"""No GPU, databases or production requests; a deterministic upstream exercises the real relay."""
import asyncio
import json
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.routers.voiceRouter import VoiceSettings, create_voice_router

ORIGIN = "http://localhost:3000"
SETTINGS = VoiceSettings(enabled=True)


class Upstream:
    def __init__(self, mode="normal"):
        self.mode = mode
        self.frames = []
        self.closed = False
        self.results = asyncio.Queue()

    async def recv(self):
        return json.dumps({"type": "config", "sampleRate": 16000, "useAudioWorklet": True})

    async def send(self, frame):
        self.frames.append(frame)
        if frame:
            await self.results.put({"lines": [], "buffer_transcription": "공구 오"})
        elif self.mode != "hang":
            await self.results.put({"lines": [{"text": "공구 오류 원인"}], "buffer_transcription": ""})
            if self.mode != "no_ack":
                await self.results.put({"type": "ready_to_stop"})

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.mode == "fail":
            raise OSError("private upstream address should not be disclosed")
        return json.dumps(await self.results.get())


def fixture(settings=SETTINGS, mode="normal"):
    upstreams = []

    @asynccontextmanager
    async def connector(url, **kwargs):
        assert kwargs["origin"] == "http://voice-gateway.internal"
        upstream = Upstream(mode)
        upstreams.append(upstream)
        try:
            yield upstream
        finally:
            upstream.closed = True

    app = FastAPI()
    app.include_router(create_voice_router(settings, connector))
    return TestClient(app), upstreams


def reserve(client, **headers):
    return client.post("/api/voice/sessions", headers={"origin": ORIGIN, **headers})


def socket(client, token, **headers):
    return client.websocket_connect("/api/voice/stream", subprotocols=["voice.v1", "ticket." + token],
                                    headers={"origin": ORIGIN, **headers})


def test_disabled_and_unknown_origin_are_rejected():
    client, _ = fixture(VoiceSettings())
    with client:
        assert reserve(client).status_code == 503
    client, _ = fixture()
    with client:
        assert reserve(client, origin="https://attacker.example").status_code == 403
        assert client.post("/api/voice/sessions").status_code == 403


def test_public_deployment_requires_private_proxy_key():
    cfg = replace(SETTINGS, origins=("https://voice.example.com",))
    client, _ = fixture(cfg)
    with client:
        assert reserve(client, origin=cfg.origins[0]).status_code == 503
    client, _ = fixture(replace(cfg, gateway_key="x" * 48))
    with client:
        assert reserve(client, origin=cfg.origins[0]).status_code == 403
        reply = reserve(client, origin=cfg.origins[0], **{"x-voice-gateway-key": "x" * 48})
        assert reply.status_code == 201
        with pytest.raises(WebSocketDisconnect):
            with socket(client, reply.json()["ticket"], origin=cfg.origins[0]):
                pass


def test_pcm_partial_final_ack_and_ticket_consumption():
    client, upstreams = fixture()
    with client:
        reply = reserve(client)
        assert reply.headers["cache-control"] == "no-store"
        token = reply.json()["ticket"]
        with socket(client, token) as ws:
            assert ws.accepted_subprotocol == "voice.v1"
            assert ws.receive_json()["sampleRate"] == 16000
            assert reserve(client).status_code == 429
            with pytest.raises(WebSocketDisconnect):
                with socket(client, token):
                    pass
            ws.send_bytes(b"\x01\x00" * 1600)
            assert ws.receive_json()["buffer_transcription"] == "공구 오"
            ws.send_bytes(b"")
            assert ws.receive_json()["lines"][0]["text"] == "공구 오류 원인"
            assert ws.receive_json()["type"] == "ready_to_stop"
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 1000
        assert upstreams[0].frames == [b"\x01\x00" * 1600, b""]
        assert upstreams[0].closed
        with pytest.raises(WebSocketDisconnect):
            with socket(client, token):
                pass
        assert reserve(client).status_code == 201


@pytest.mark.parametrize("frame", [b"x", b"\0" * 32002, "not pcm"], ids=["odd-byte", "oversized", "text"])
def test_invalid_frames_release_capacity(frame):
    client, upstreams = fixture()
    with client:
        with socket(client, reserve(client).json()["ticket"]) as ws:
            ws.receive_json()
            if isinstance(frame, bytes):
                ws.send_bytes(frame)
            else:
                ws.send_text(frame)
            assert ws.receive_json()["type"] == "error"
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        assert upstreams[0].closed
        assert reserve(client).status_code == 201


@pytest.mark.parametrize("mode", ["hang", "no_ack"])
def test_final_drain_needs_ack_and_has_timeout(mode):
    client, upstreams = fixture(replace(SETTINGS, drain_seconds=.03), mode)
    with client:
        with socket(client, reserve(client).json()["ticket"]) as ws:
            ws.receive_json()
            ws.send_bytes(b"")
            if mode == "no_ack":
                ws.receive_json()
            assert ws.receive_json()["type"] == "error"
        assert upstreams[0].closed


@pytest.mark.parametrize("send_eof", [False, True])
def test_disconnect_releases_upstream_including_drain(send_eof):
    client, upstreams = fixture(mode="hang")
    with client:
        with socket(client, reserve(client).json()["ticket"]) as ws:
            ws.receive_json()
            if send_eof:
                ws.send_bytes(b"")
        assert upstreams[0].closed
        assert reserve(client).status_code == 201


def test_abandoned_reservation_expires_and_cannot_be_used():
    client, _ = fixture(replace(SETTINGS, ticket_seconds=.02))
    with client:
        token = reserve(client).json()["ticket"]
        assert reserve(client).status_code == 429
        time.sleep(.03)
        with pytest.raises(WebSocketDisconnect):
            with socket(client, token):
                pass
        assert reserve(client).status_code == 201


def test_upstream_failure_is_generic_and_releases_slot():
    client, upstreams = fixture(mode="fail")
    with client:
        with socket(client, reserve(client).json()["ticket"]) as ws:
            ws.receive_json()
            error = ws.receive_json()
            assert error["type"] == "error"
            assert "private" not in error["error"]
        assert upstreams[0].closed
        assert reserve(client).status_code == 201


def test_rate_limit_rejects_audio_flood():
    client, _ = fixture()
    with client:
        with socket(client, reserve(client).json()["ticket"]) as ws:
            ws.receive_json()
            for _ in range(6):
                ws.send_bytes(b"\0" * 32000)
            while True:
                message = ws.receive_json()
                if message.get("type") == "error":
                    assert "속도" in message["error"]
                    break
