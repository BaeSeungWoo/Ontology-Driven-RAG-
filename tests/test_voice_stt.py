import asyncio
import threading
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from services.stt.server import Settings, create_app

ORIGIN = {"origin": "http://voice-gateway.internal"}


class Result:
    def __init__(self, data): self.data = data
    def to_dict(self): return self.data


class Processor:
    def __init__(self, fail=False, stall=False):
        self.queue = asyncio.Queue()
        self.frames = []
        self.cleaned = False
        self.fail = fail
        self.stall = stall

    async def create_tasks(self):
        async def results():
            while True:
                data = await self.queue.get()
                if data is None: return
                yield Result(data)
        return results()

    async def process_audio(self, frame):
        self.frames.append(frame)
        if frame:
            await self.queue.put({"status": "error"} if self.fail else {
                "lines": [], "buffer_transcription": "안녕", "remaining_time_transcription": .2})
        elif not self.stall:
            await self.queue.put({"lines": [{"speaker": 1, "text": "안녕하세요", "start": "0:00:00"}], "buffer_transcription": ""})
            await self.queue.put(None)

    async def cleanup(self): self.cleaned = True


class Runtime:
    info = {"model": "test-double", "device": "test-only"}
    def __init__(self, fail=False, stall=False):
        self.processors = []
        self.final_audio = []
        self.fail, self.stall = fail, stall
    def processor(self):
        result = Processor(self.fail, self.stall)
        self.processors.append(result)
        return result

    def finalize(self, pcm):
        self.final_audio.append(pcm)
        return "공구가 등록되지 않았다는 오류가 발생했습니다."


def client(runtime=None, **overrides):
    runtime = runtime or Runtime()
    app = create_app(replace(Settings(), **overrides), lambda _: runtime)
    return TestClient(app), runtime


def test_final_audio_drains_before_ready_and_slot_is_reusable():
    c, runtime = client()
    with c:
        assert c.get("/health").status_code == 200
        for _ in range(2):
            with c.websocket_connect("/asr", headers=ORIGIN) as ws:
                assert ws.receive_json()["sampleRate"] == 16000
                ws.send_bytes(b"\x01\x00" * 1600)
                assert ws.receive_json()["buffer_transcription"] == "안녕"
                ws.send_bytes(b"")
                final = ws.receive_json()
                assert final["lines"][0]["text"] == "안녕하세요"
                reconciled = ws.receive_json()
                assert reconciled["type"] == "final"
                assert reconciled["lines"][0]["text"] == "공구가 등록되지 않았다는 오류가 발생했습니다."
                assert reconciled["buffer_transcription"] == ""
                assert runtime.final_audio[-1] == b"\x01\x00" * 1600
                assert ws.receive_json() == {"type": "ready_to_stop"}
            assert runtime.processors[-1].cleaned
        assert c.get("/health").json()["active_sessions"] == 0


@pytest.mark.parametrize("origin", ["https://evil.example", "null", ""])
def test_rejects_untrusted_websites(origin):
    c, runtime = client()
    with c, pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/asr", headers={"origin": origin}): pass
    assert not runtime.processors


def test_capacity_rejection_does_not_start_another_processor():
    c, runtime = client()
    with c, c.websocket_connect("/asr", headers=ORIGIN) as first:
        first.receive_json()
        with c.websocket_connect("/asr", headers=ORIGIN) as second:
            assert second.receive_json()["type"] == "error"
        assert len(runtime.processors) == 1


@pytest.mark.parametrize("frame", [b"\x01", b"\x00" * 32002, "invalid text"], ids=["odd-byte", "oversized", "text-frame"])
def test_rejects_invalid_audio(frame):
    c, runtime = client()
    with c:
        with c.websocket_connect("/asr", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_text(frame) if isinstance(frame, str) else ws.send_bytes(frame)
            assert ws.receive_json()["type"] == "error"
        assert runtime.processors[0].cleaned


def test_worker_error_is_reported_without_waiting_for_more_microphone_input():
    c, runtime = client(Runtime(fail=True))
    with c, c.websocket_connect("/asr", headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00\x00")
        assert ws.receive_json()["type"] == "error"


def test_drain_timeout_reports_incomplete_instead_of_ready():
    c, runtime = client(Runtime(stall=True), drain_timeout=.02)
    with c:
        with c.websocket_connect("/asr", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_bytes(b"")
            assert ws.receive_json()["type"] == "error"
        assert runtime.processors[0].cleaned


def test_disconnect_releases_microphone_session():
    c, runtime = client()
    with c:
        with c.websocket_connect("/asr", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_bytes(b"\x00\x00")
            ws.receive_json()
        assert runtime.processors[0].cleaned
        assert c.get("/health").json()["active_sessions"] == 0


def test_audio_duration_limit():
    c, _ = client(max_seconds=.01)
    with c, c.websocket_connect("/asr", headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x00" * 3200)
        assert ws.receive_json()["type"] == "error"


def test_cancelling_during_drain_releases_gpu_slot_without_waiting_for_timeout():
    c, runtime = client(Runtime(stall=True), drain_timeout=60)
    with c:
        with c.websocket_connect("/asr", headers=ORIGIN) as ws:
            ws.receive_json()
            ws.send_bytes(b"")
        assert runtime.processors[0].cleaned
        assert c.get("/health").json()["active_sessions"] == 0


def test_finalization_receives_exact_original_frames_and_replaces_snapshot():
    c, runtime = client()
    frames = [b"\x01\x00" * 1200, b"\x03\x00" * 160]
    with c, c.websocket_connect("/asr", headers=ORIGIN) as ws:
        ws.receive_json()
        for frame in frames:
            ws.send_bytes(frame)
            ws.receive_json()
        ws.send_bytes(b"")
        messages = []
        while True:
            item = ws.receive_json()
            messages.append(item)
            if item.get("type") == "ready_to_stop": break
        assert runtime.final_audio == [b"".join(frames)]
        assert messages[-2]["type"] == "final"
        assert messages[-2]["lines"][0]["text"] == runtime.finalize(b"")


@pytest.mark.parametrize("failure", ["empty", "exception"])
def test_finalization_failure_never_accepts_provisional_text(failure):
    runtime = Runtime()
    def finalize(pcm):
        if failure == "exception": raise RuntimeError("GPU failure")
        return "  "
    runtime.finalize = finalize
    c, _ = client(runtime)
    with c, c.websocket_connect("/asr", headers=ORIGIN) as ws:
        ws.receive_json()
        ws.send_bytes(b"\x01\x00")
        ws.receive_json()
        ws.send_bytes(b"")
        assert "lines" in ws.receive_json()
        assert ws.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect): ws.receive_json()


@pytest.mark.parametrize("mode", ["disconnect", "timeout"])
def test_final_worker_keeps_capacity_until_it_actually_finishes(mode):
    runtime = Runtime()
    started, release = threading.Event(), threading.Event()
    def finalize(pcm):
        started.set()
        if not release.wait(5): raise RuntimeError("test did not release worker")
        return "최종 질문"
    runtime.finalize = finalize
    c, _ = client(runtime, drain_timeout=.1 if mode == "timeout" else 60)
    with c:
        try:
            with c.websocket_connect("/asr", headers=ORIGIN) as ws:
                ws.receive_json()
                ws.send_bytes(b"\x01\x00")
                ws.receive_json()
                ws.send_bytes(b"")
                ws.receive_json()
                assert started.wait(2)
                if mode == "timeout": assert ws.receive_json()["type"] == "error"
            assert c.get("/health").json()["active_sessions"] == 1
            with c.websocket_connect("/asr", headers=ORIGIN) as rejected:
                assert rejected.receive_json()["type"] == "error"
            assert len(runtime.processors) == 1
        finally:
            release.set()
        deadline = time.monotonic() + 2
        while c.get("/health").json()["active_sessions"] and time.monotonic() < deadline:
            time.sleep(.01)
        assert c.get("/health").json()["active_sessions"] == 0
