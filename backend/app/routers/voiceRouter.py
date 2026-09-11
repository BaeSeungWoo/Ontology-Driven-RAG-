"""Short-lived voice tickets and a bounded PCM relay. Run ONE backend worker.

The existing RAG request/history APIs remain the only path that submits a question.
No audio, tickets, or transcripts are persisted or logged here.
"""
import asyncio
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlparse

from anyio import CancelScope
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VoiceSettings:
    enabled: bool = False
    origins: tuple[str, ...] = ("http://localhost:3000", "http://127.0.0.1:3000")
    upstream: str = "ws://127.0.0.1:8090/asr"
    gateway_key: str = ""
    capacity: int = 1
    max_seconds: int = 180
    ticket_seconds: float = 30
    idle_seconds: float = 30
    drain_seconds: float = 60

    @classmethod
    def from_env(cls):
        return cls(
            enabled=os.getenv("VOICE_ENABLED", "false").lower() == "true",
            origins=tuple(x.strip() for x in os.getenv("VOICE_ALLOWED_ORIGINS", ",".join(cls.origins)).split(",") if x.strip()),
            upstream=os.getenv("VOICE_STT_URL", cls.upstream),
            gateway_key=os.getenv("VOICE_GATEWAY_KEY", ""),
            capacity=int(os.getenv("VOICE_MAX_SESSIONS", "1")),
            max_seconds=int(os.getenv("VOICE_MAX_SECONDS", "180")),
        )

    def validate(self):
        if not self.enabled:
            raise HTTPException(503, "음성 입력이 아직 활성화되지 않았습니다.")
        if not self.origins or not 1 <= self.capacity <= 8 or not 15 <= self.max_seconds <= 600:
            raise HTTPException(503, "음성 서버 설정을 확인해 주세요.")
        # A public origin needs the private reverse-proxy key. Origin itself is not authentication.
        local = all(urlparse(o).hostname in ("localhost", "127.0.0.1", "::1") for o in self.origins)
        if (not local and len(self.gateway_key) < 32) or "*" in self.origins:
            raise HTTPException(503, "음성 서비스의 접근 제어 설정이 필요합니다.")
        if urlparse(self.upstream).scheme not in ("ws", "wss"):
            raise HTTPException(503, "음성 서버 주소 설정을 확인해 주세요.")


@dataclass
class Ticket:
    origin: str
    expires: float
    active: bool = False


class VoiceFailure(Exception):
    pass


def create_voice_router(settings=None, connector=connect):
    router = APIRouter(prefix="/api/voice", tags=["voice"])
    tickets: dict[str, Ticket] = {}

    def config():
        # main.py loads dotenv after importing routers; read lazily, not at import time.
        try:
            value = settings or VoiceSettings.from_env()
            value.validate()
            return value
        except ValueError:
            raise HTTPException(503, "음성 서버 설정을 확인해 주세요.") from None

    def authorize(headers, cfg):
        origin = headers.get("origin", "")
        if origin not in cfg.origins:
            raise HTTPException(403, "허용되지 않은 음성 접속 주소입니다.")
        if cfg.gateway_key and not secrets.compare_digest(headers.get("x-voice-gateway-key", ""), cfg.gateway_key):
            raise HTTPException(403, "음성 서비스 접근 권한이 없습니다.")
        return origin

    @router.post("/sessions", status_code=201)
    async def new_session(request: Request):
        cfg = config()
        origin = authorize(request.headers, cfg)
        now = time.monotonic()
        for token, ticket in list(tickets.items()):
            if not ticket.active and ticket.expires <= now:
                del tickets[token]
        # No await between capacity check and reservation, in this single event loop.
        if len(tickets) >= cfg.capacity:
            raise HTTPException(429, "음성 인식이 사용 중입니다. 잠시 후 다시 시도해 주세요.")
        token = secrets.token_urlsafe(32)
        tickets[token] = Ticket(origin, now + cfg.ticket_seconds)
        from fastapi.responses import JSONResponse
        return JSONResponse({"ticket": token, "max_seconds": cfg.max_seconds}, status_code=201,
                            headers={"Cache-Control": "no-store"})

    @router.websocket("/stream")
    async def stream(ws: WebSocket):
        try:
            cfg = config()
            origin = authorize(ws.headers, cfg)
        except HTTPException:
            await ws.close(code=1008)
            return
        protocols = ws.scope.get("subprotocols", [])
        tokens = [p[7:] for p in protocols if p.startswith("ticket.")]
        token = tokens[0] if len(tokens) == 1 else ""
        ticket = tickets.get(token)
        if "voice.v1" not in protocols or not ticket or ticket.active or ticket.expires <= time.monotonic() or ticket.origin != origin:
            await ws.close(code=1008)
            return
        ticket.active = True
        tasks = []
        eof = asyncio.Event()
        try:
            await ws.accept(subprotocol="voice.v1")
            async with connector(cfg.upstream, origin="http://voice-gateway.internal",
                                 open_timeout=10, close_timeout=3, max_size=2**20,
                                 max_queue=8, write_limit=32768) as upstream:
                first = json.loads(await asyncio.wait_for(upstream.recv(), 15))
                if first.get("type") != "config" or first.get("sampleRate") != 16000 or not first.get("useAudioWorklet"):
                    raise VoiceFailure("음성 서버를 준비하지 못했습니다. 잠시 후 다시 시도해 주세요.")
                await ws.send_json(first)
                started = time.monotonic()

                async def receive_audio():
                    total = 0
                    while True:
                        msg = await asyncio.wait_for(ws.receive(), cfg.idle_seconds)
                        if msg["type"] == "websocket.disconnect":
                            raise WebSocketDisconnect(msg.get("code", 1000))
                        frame = msg.get("bytes")
                        if frame is None or len(frame) % 2 or len(frame) > 32000:
                            raise VoiceFailure("올바르지 않은 마이크 음성 형식입니다.")
                        if eof.is_set():
                            raise VoiceFailure("종료한 음성 세션에 입력할 수 없습니다.")
                        elapsed = time.monotonic() - started
                        total += len(frame)
                        if elapsed > cfg.max_seconds + 5 or total > cfg.max_seconds * 32000 or total / 32000 > elapsed + 5:
                            raise VoiceFailure("음성 입력 시간 또는 전송 속도를 초과했습니다.")
                        if not frame:
                            eof.set()
                        await asyncio.wait_for(upstream.send(frame), 5)
                        if not frame:
                            # Keep observing cancellation while the final ASR results drain.
                            return

                async def receive_results():
                    async for message in upstream:
                        data = json.loads(message)
                        if data.get("type") == "error" or data.get("status") == "error" or data.get("error"):
                            raise VoiceFailure("음성 인식에 실패했습니다. 잠시 후 다시 시도해 주세요.")
                        if float(data.get("remaining_time_transcription") or 0) > 15:
                            raise VoiceFailure("음성 인식 처리가 지연되었습니다. 다시 시도해 주세요.")
                        if data.get("type") == "ready_to_stop":
                            if not eof.is_set():
                                raise VoiceFailure("음성 인식이 예기치 않게 종료되었습니다.")
                            await ws.send_json(data)
                            return
                        await ws.send_json(data)
                    raise VoiceFailure("음성 서버 연결이 종료되었습니다.")

                async def watch_disconnect():
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        raise WebSocketDisconnect(msg.get("code", 1000))
                    raise VoiceFailure("종료한 음성 세션에 입력할 수 없습니다.")

                reader = asyncio.create_task(receive_audio())
                writer = asyncio.create_task(receive_results())
                tasks = [reader, writer]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED,
                                             timeout=cfg.max_seconds + 10)
                if not done:
                    raise VoiceFailure("음성 입력 시간이 초과되었습니다.")
                if reader in done:
                    await reader
                    watcher = asyncio.create_task(watch_disconnect())
                    tasks.append(watcher)
                    done, _ = await asyncio.wait([writer, watcher], return_when=asyncio.FIRST_COMPLETED,
                                                 timeout=cfg.drain_seconds)
                    if not done:
                        raise VoiceFailure("마지막 음성 처리 시간이 초과되었습니다.")
                    if watcher in done:
                        await watcher
                    await writer
                else:
                    await writer
                await ws.close(code=1000)
        except WebSocketDisconnect:
            pass
        except Exception as exc:
            if not isinstance(exc, (VoiceFailure, TimeoutError)):
                log.warning("Voice relay failed (%s)", type(exc).__name__)
            message = str(exc) if isinstance(exc, VoiceFailure) else "음성 서버 연결 또는 처리 시간이 초과되었습니다. 다시 시도해 주세요."
            try:
                await ws.send_json({"type": "error", "error": message})
                await ws.close(code=1011)
            except (RuntimeError, WebSocketDisconnect, OSError):
                pass
        finally:
            # ASGI cancellation must not interrupt resource/accounting cleanup.
            with CancelScope(shield=True):
                try:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                finally:
                    tickets.pop(token, None)

    return router


voiceRouter = create_voice_router()
