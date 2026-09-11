"""Single-worker Korean microphone STT server; run with uvicorn server:app."""
import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version
from threading import Lock

from anyio import CancelScope
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

log = logging.getLogger("korean_stt")
BYTES_PER_SECOND = 32000
_ENGINE_INIT_LOCK = Lock()


def create_fp16_engine(config):
    """Adapt WLK 0.2.26's auto-only loader before it loads/warms the model.

    This release doesn't forward compute_type from its public config. Scope the
    backend-class replacement to startup and restore it even when loading fails.
    """
    if version("whisperlivekit") != "0.2.26":
        raise RuntimeError("The FP16 adapter requires whisperlivekit==0.2.26; use requirements.lock.")
    from faster_whisper import WhisperModel
    from whisperlivekit import TranscriptionEngine
    from whisperlivekit.local_agreement import whisper_online

    with _ENGINE_INIT_LOCK:
        original = whisper_online.FasterWhisperASR

        class CudaFP16ASR(original):
            def load_model(self, model_size=None, cache_dir=None, model_dir=None):
                reference = model_dir or model_size
                if not reference:
                    raise ValueError("A local model path or model name is required")
                return WhisperModel(reference, device="cuda", compute_type="float16",
                                    download_root=cache_dir)

        whisper_online.FasterWhisperASR = CudaFP16ASR
        try:
            return TranscriptionEngine(config=config)
        finally:
            whisper_online.FasterWhisperASR = original


@dataclass(frozen=True)
class Settings:
    model: str = "turbo"
    origins: tuple[str, ...] = ("http://voice-gateway.internal",)
    max_sessions: int = 1
    drain_timeout: float = 60
    idle_timeout: float = 30
    max_seconds: float = 600
    max_lag: float = 15
    finalize_audio: bool = True

    @classmethod
    def from_env(cls):
        model = os.getenv("STT_MODEL", "turbo")
        if model not in ("turbo", "large-v3"):
            raise ValueError("STT_MODEL must be turbo or large-v3")
        sessions = int(os.getenv("STT_MAX_SESSIONS", "1"))
        if not 1 <= sessions <= 8:
            raise ValueError("STT_MAX_SESSIONS must be between 1 and 8")
        return cls(model=model, max_sessions=sessions, origins=tuple(
            x.strip() for x in os.getenv("STT_ORIGINS", ",".join(cls.origins)).split(",") if x.strip()
        ))


class LiveRuntime:
    """Imports/downloads GPU dependencies only during real application startup."""
    def __init__(self, settings):
        import ctranslate2
        from huggingface_hub import snapshot_download
        from whisperlivekit import AudioProcessor
        from whisperlivekit.config import WhisperLiveKitConfig

        if ctranslate2.get_cuda_device_count() < 1:
            raise RuntimeError("NVIDIA CUDA GPU not found. Check the driver and Docker GPU passthrough.")
        models = {
            "turbo": ("mobiuslabsgmbh/faster-whisper-large-v3-turbo", "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf"),
            "large-v3": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
        }
        repo, revision = models[settings.model]
        model_dir = snapshot_download(repo, revision=revision, allow_patterns=[
            "model.bin", "config.json", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"
        ])
        config = WhisperLiveKitConfig(
            model_size=settings.model, model_dir=model_dir,
            backend="faster-whisper", backend_policy="localagreement", lan="ko",
            pcm_input=True, vac=False, vad=True, diarization=False,
            min_chunk_size=0.5, buffer_trimming="segment", buffer_trimming_sec=15,
            pause_segmentation_seconds=0.7, log_level="WARNING",
        )
        self.engine = create_fp16_engine(config)
        self.processor_type = AudioProcessor
        actual = self.engine.asr.model.model
        # Check the actual runtime after explicitly requesting CUDA/FP16.
        if actual.device != "cuda" or actual.compute_type != "float16":
            raise RuntimeError(f"Expected CUDA/float16, received {actual.device}/{actual.compute_type}")
        self.info = {"model": settings.model, "device": actual.device,
                     "compute_type": actual.compute_type, "backend": "faster-whisper",
                     "policy": "localagreement", "language": "ko", "revision": revision,
                     "vac": False, "vad": True,
                     "finalization": "full_audio_v1" if settings.finalize_audio else "stream_only"}
        log.info("STT ready: %s", self.info)

    def processor(self):
        return self.processor_type(transcription_engine=self.engine, language="ko", mode="full", pcm_input=True)

    def finalize(self, pcm):
        """Re-decode original PCM, independent of provisional streaming text.

        Match the whole-file settings validated on the GPU. This reuses the
        loaded model; no second model or audio file is created.
        """
        import numpy as np
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
        segments, _ = self.engine.asr.model.transcribe(
            audio, language="ko", beam_size=5, word_timestamps=True,
            initial_prompt=None, condition_on_previous_text=True, vad_filter=True,
        )
        return " ".join(segment.text.strip() for segment in segments if segment.text.strip())


class SessionError(Exception):
    pass


def create_app(settings=None, runtime_factory=LiveRuntime):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.runtime = await asyncio.to_thread(runtime_factory, settings)
        app.state.active = 0
        app.state.final_jobs = set()
        try:
            yield
        finally:
            # CUDA work in a thread cannot be cancelled by cancelling its awaiter.
            if app.state.final_jobs:
                await asyncio.gather(*app.state.final_jobs, return_exceptions=True)

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health():
        return {"ready": True, "active_sessions": app.state.active, **app.state.runtime.info}

    @app.websocket("/asr")
    async def transcribe(ws: WebSocket):
        # Default distribution listens only on localhost. Also reject cross-site use.
        if ws.headers.get("origin") not in settings.origins:
            await ws.close(code=1008)
            return
        await ws.accept()
        if app.state.active >= settings.max_sessions:
            await ws.send_json({"type": "error", "error": "사용 중인 인식 세션이 있습니다. 잠시 후 다시 시작하세요."})
            await ws.close(code=1013)
            return
        app.state.active += 1  # No await between the capacity check and reservation.
        processor = None
        tasks = []
        pcm = bytearray()
        final_job = None
        try:
            processor = app.state.runtime.processor()
            results = await processor.create_tasks()
            await ws.send_json({"type": "config", "useAudioWorklet": True,
                                "sampleRate": 16000, "mode": "full", "maxSeconds": settings.max_seconds})
            started = time.monotonic()

            async def receive():
                total = 0
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), settings.idle_timeout)
                    except TimeoutError:
                        raise SessionError("마이크 입력이 중단되었습니다. 연결을 다시 시작하세요.")
                    if msg["type"] == "websocket.disconnect":
                        raise WebSocketDisconnect(msg.get("code", 1000))
                    frame = msg.get("bytes")
                    if frame is None or len(frame) % 2 or len(frame) > BYTES_PER_SECOND:
                        raise SessionError("16kHz 모노 PCM 음성 형식이 올바르지 않습니다.")
                    if not frame:
                        await processor.process_audio(b"")
                        return
                    total += len(frame)
                    elapsed = time.monotonic() - started
                    if total / BYTES_PER_SECOND > settings.max_seconds or elapsed > settings.max_seconds + 10:
                        raise SessionError("음성 입력 시간이 초과되었습니다. 새 음성 입력을 시작하세요.")
                    if total / BYTES_PER_SECOND > elapsed + 5:
                        raise SessionError("실시간 속도를 초과한 음성 입력입니다.")
                    if settings.finalize_audio:
                        pcm.extend(frame)
                    await processor.process_audio(frame)

            async def send():
                async for result in results:
                    data = result.to_dict()
                    if data.get("status") == "error" or data.get("error"):
                        raise SessionError("음성 인식에 실패했습니다. 서버 로그를 확인하세요.")
                    if float(data.get("remaining_time_transcription") or 0) > settings.max_lag:
                        raise SessionError("인식 지연이 너무 큽니다. 동시 접속 수를 줄여주세요.")
                    await ws.send_json(data)

            async def watch_disconnect():
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    raise WebSocketDisconnect(msg.get("code", 1000))
                raise SessionError("종료한 음성 세션에 입력할 수 없습니다.")

            reader = asyncio.create_task(receive())
            writer = asyncio.create_task(send())
            tasks = [reader, writer]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if reader in done:
                await reader  # Propagate disconnect/invalid input before reporting success.
                deadline = time.monotonic() + settings.drain_timeout
                watcher = asyncio.create_task(watch_disconnect())
                tasks.append(watcher)
                drained, _ = await asyncio.wait([writer, watcher], return_when=asyncio.FIRST_COMPLETED,
                                                timeout=settings.drain_timeout)
                if not drained:
                    raise SessionError("마지막 음성 처리 시간이 초과되었습니다. 미확정 자막을 확인하세요.")
                if watcher in drained:
                    await watcher
                await writer
                if settings.finalize_audio:
                    if not pcm:
                        raise SessionError("인식할 음성이 없습니다. 마이크를 확인하세요.")
                    final_job = asyncio.create_task(asyncio.to_thread(app.state.runtime.finalize, bytes(pcm)))
                    pcm.clear()
                    app.state.final_jobs.add(final_job)
                    final_job.add_done_callback(app.state.final_jobs.discard)
                    finished, _ = await asyncio.wait(
                        [final_job, watcher], return_when=asyncio.FIRST_COMPLETED,
                        timeout=max(0, deadline - time.monotonic()),
                    )
                    if watcher in finished:
                        await watcher
                    if final_job not in finished:
                        raise SessionError("최종 음성 인식 시간이 초과되었습니다. 다시 입력하세요.")
                    text = (await final_job).strip()
                    if not text:
                        raise SessionError("최종 인식 결과가 없습니다. 다시 입력하세요.")
                    # Full snapshot replacement: no older provisional message
                    # can overwrite this because the streaming writer is done.
                    await ws.send_json({"type": "final", "lines": [{"speaker": 1, "text": text}],
                                        "buffer_transcription": "", "finalization": "full_audio_v1"})
                await ws.send_json({"type": "ready_to_stop"})
                await ws.close(code=1000)
            else:
                await writer
                raise SessionError("인식 파이프라인이 예기치 않게 종료되었습니다.")
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            if not isinstance(exc, SessionError):
                log.exception("STT session failed")
            error = str(exc) if isinstance(exc, SessionError) else "서버 처리 오류입니다. 서버 로그를 확인하세요."
            try:
                await ws.send_json({"type": "error", "error": error})
                await ws.close(code=1011)
            except (RuntimeError, WebSocketDisconnect):
                pass
        finally:
            with CancelScope(shield=True):
                try:
                    for task in tasks:
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    if processor:
                        await asyncio.wait_for(processor.cleanup(), 10)
                except Exception:
                    log.exception("STT session cleanup failed")
                finally:
                    pcm.clear()
                    if final_job is not None and not final_job.done():
                        # A closed/timed-out client must not free a GPU slot
                        # while its uncancellable worker is still running.
                        def release_when_finished(job):
                            job.exception() if not job.cancelled() else None
                            app.state.active -= 1
                        final_job.add_done_callback(release_when_finished)
                    else:
                        if final_job is not None and not final_job.cancelled():
                            final_job.exception()
                        app.state.active -= 1

    return app


app = create_app()
