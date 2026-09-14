"""Regression: WLK's auto loader may choose int8_float16 on a CUDA GPU."""
import sys
from types import ModuleType, SimpleNamespace

import pytest

from services.stt import server


def stub_runtime(monkeypatch, *, fail=False):
    calls = []
    faster = ModuleType("faster_whisper")

    def model(reference, **kwargs):
        calls.append((reference, kwargs))
        if fail:
            raise RuntimeError("load failed")
        return SimpleNamespace(device=kwargs["device"], compute_type=kwargs["compute_type"])

    faster.WhisperModel = model
    online = ModuleType("whisperlivekit.local_agreement.whisper_online")

    class AutoASR:
        def __init__(self, lan=None, model_size=None, model_dir=None, cache_dir=None):
            self.model = self.load_model(model_size, cache_dir, model_dir)

        def load_model(self, model_size=None, cache_dir=None, model_dir=None):
            # Emulate the production failure if our adapter isn't used.
            return model(model_dir or model_size, device="cuda", compute_type="int8_float16")

    online.FasterWhisperASR = AutoASR
    package = ModuleType("whisperlivekit")

    def engine(config):
        asr = online.FasterWhisperASR(lan="ko", model_size="turbo", model_dir=config.model_dir)
        return SimpleNamespace(asr=asr)

    package.TranscriptionEngine = engine
    local = ModuleType("whisperlivekit.local_agreement")
    local.whisper_online = online
    for name, module in [("faster_whisper", faster), ("whisperlivekit", package),
                         ("whisperlivekit.local_agreement", local)]:
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setattr(server, "version", lambda name: "0.2.26")
    return calls, online, AutoASR


def test_forces_fp16_before_model_construction_and_restores_backend(monkeypatch):
    calls, online, original = stub_runtime(monkeypatch)
    result = server.create_fp16_engine(SimpleNamespace(model_dir="/models/pinned-revision"))
    assert result.asr.model.device == "cuda"
    assert result.asr.model.compute_type == "float16"
    assert calls == [("/models/pinned-revision", {"device": "cuda", "compute_type": "float16", "download_root": None})]
    assert online.FasterWhisperASR is original


def test_restores_backend_if_loading_fails(monkeypatch):
    _, online, original = stub_runtime(monkeypatch, fail=True)
    with pytest.raises(RuntimeError, match="load failed"):
        server.create_fp16_engine(SimpleNamespace(model_dir="/models/test"))
    assert online.FasterWhisperASR is original


def test_rejects_untested_wlk_release(monkeypatch):
    monkeypatch.setattr(server, "version", lambda name: "0.2.27")
    with pytest.raises(RuntimeError, match="0.2.26"):
        server.create_fp16_engine(SimpleNamespace(model_dir="/models/test"))


def test_final_pass_uses_original_pcm_without_streaming_prompt():
    np = pytest.importorskip("numpy")
    calls = []
    consumed = []
    def transcribe(audio, **options):
        calls.append((audio.copy(), options))
        def segments():
            consumed.append(True)
            yield SimpleNamespace(text=" 공구가 등록되지 않았습니다. ")
            yield SimpleNamespace(text=" 원인을 알려주세요. ")
        return segments(), None
    runtime = server.LiveRuntime.__new__(server.LiveRuntime)
    runtime.engine = SimpleNamespace(asr=SimpleNamespace(model=SimpleNamespace(transcribe=transcribe)))
    pcm = np.array([-32768, 0, 32767], dtype="<i2").tobytes()
    result = runtime.finalize(pcm)
    assert result == "공구가 등록되지 않았습니다. 원인을 알려주세요."
    np.testing.assert_array_equal(calls[0][0], np.array([-1, 0, 32767/32768], dtype=np.float32))
    assert calls[0][1]["initial_prompt"] is None
    assert calls[0][1]["language"] == "ko"
    assert calls[0][1]["vad_filter"] is True
    assert consumed == [True]
