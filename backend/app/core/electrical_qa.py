"""Run each machine's drawing engine in an isolated process."""
import asyncio
import json
import logging
import os
import re
from pathlib import Path
import subprocess
import sys
from time import monotonic

PACKAGE = Path(__file__).resolve().parents[2] / "vendor" / "electrical_qa"
MACHINE_CONFIGS = {"M005": "config.json", "M051": "config.json"}
SUPPORTED_MACHINES = set(MACHINE_CONFIGS)
DISABLED_MESSAGE = "기술엔지니어 모드는 연암(기존)에서만 사용할 수 있습니다."
QUESTIONS = [
    "장비가 동작하지 않을 때 전기도면에서 무엇부터 확인해야 하나요?",
    "모터나 펌프가 작동하지 않을 때 관련 회로를 어떻게 점검하나요?",
    "센서와 제어 신호의 연결 관계를 전기도면으로 확인하고 싶어요.",
]


def validate_machine(machine_code):
    if machine_code not in SUPPORTED_MACHINES:
        raise ValueError("전기도면 고장진단 QA는 M005 · DHF8000, M051 · DHF8000 #2를 지원합니다.")


def config_for_machine(machine_code):
    validate_machine(machine_code)
    return Path(os.environ.get("ELECTRICAL_QA_CONFIG", PACKAGE / MACHINE_CONFIGS[machine_code])).resolve()


async def electrical_response(request, events):
    """Progress frames precede the existing metadata + answer wire format."""
    pending = None
    status = "전기도면 QA를 준비하는 중"
    last_sent = monotonic()
    try:
        yield "PROGRESS:" + json.dumps(status, ensure_ascii=False) + "\n\n"
        while True:
            if pending is None:
                pending = asyncio.create_task(anext(events))
            done, _ = await asyncio.wait({pending}, timeout=1)
            if await request.is_disconnected():
                return
            if not done:
                if monotonic() - last_sent >= 10:
                    yield "PROGRESS:" + json.dumps(status, ensure_ascii=False) + "\n\n"
                    last_sent = monotonic()
                continue
            try:
                event = pending.result()
            except StopAsyncIteration:
                break
            pending = None
            if event["type"] == "progress":
                status = event["data"]
                yield "PROGRESS:" + json.dumps(status, ensure_ascii=False) + "\n\n"
                last_sent = monotonic()
            elif event["type"] == "metadata":
                yield "METADATA:" + json.dumps(event["data"], ensure_ascii=False) + "\n\n"
            elif event["type"] == "token":
                yield event["data"]
    except Exception as exc:
        logging.getLogger(__name__).exception("Electrical QA stream failed")
        message = (str(exc) if isinstance(exc, (RuntimeError, ValueError)) else "") or "전기도면 QA 처리 중 오류가 발생했습니다. 다시 시도해 주세요."
        yield "ERROR:" + json.dumps(message, ensure_ascii=False) + "\n\n"
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await events.aclose()


async def append_manual_evidence(service, machine_code, question, result):
    if not result["chunks"]:
        return
    from pipeline.ingestion.machine_resolver import build_doc_to_machine_index, _resolve_machine_code
    documents = build_doc_to_machine_index({machine_code: service.config.machines.get(machine_code, {})})
    try:
        matches = await asyncio.to_thread(lambda: service._get_retriever("rag").search(
            query=question, machine_code=machine_code, top_k=3))
    except Exception:
        logging.getLogger(__name__).exception("Electrical QA manual retrieval failed")
        return
    citations = []
    for item in matches.items:
        source = item.metadata.get("source_doc_name", "")
        if (not source or source not in documents or machine_code not in _resolve_machine_code(source, documents)
                or re.search(r"electrical|circuit\s*diagram|전기\s*(도면|회로)", source, re.I)
                or item.metadata.get("container_type") in {"ladder", "pictures", "tables"}
                or not item.text.strip()):
            continue
        index = len(result["chunks"]) + 1
        text = item.text[:1800]
        result["chunks"].append({"index": index, "document": text,
                                 "metadata": {**item.metadata, "source_kind": "manual"}})
        citations.append(f"[chunk:{index}]")
    if citations:
        result["answer"] += "\n\n" + " ".join(citations)


async def stream_electrical(machine_code, question, *, llm_config, factory_id, history=None, user_prompt=None):
    if factory_id != "yunam_origin":
        raise ValueError(DISABLED_MESSAGE)
    validate_machine(machine_code)
    if not question.strip() or len(question) > 6000:
        raise ValueError("전기도면 질문은 1~6000자로 입력해 주세요.")
    config_path = config_for_machine(machine_code)
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith(("GRAPHRAG_", "VLLM_")) and key not in ("LLM_NAME", "PYTHONPATH")}
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    if llm_config.api_key:
        environment["OPENAI_API_KEY"] = llm_config.api_key
    # Uvicorn's Windows reload loop cannot run asyncio subprocess transports.
    process = subprocess.Popen(
        [sys.executable, str(PACKAGE / "integration_worker.py")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=PACKAGE, env=environment,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    request = json.dumps({"config_path": str(config_path), "question": question, "machine_code": machine_code,
                          "model": llm_config.model_name, "base_url": llm_config.base_url, "max_tokens": llm_config.max_tokens,
                          "history": history or [], "user_prompt": user_prompt or ""}, ensure_ascii=False).encode("utf-8")
    stderr_task = asyncio.create_task(asyncio.to_thread(process.stderr.read))
    try:
        async with asyncio.timeout(1800):
            def send_request():
                process.stdin.write(request)
                process.stdin.close()

            await asyncio.to_thread(send_request)
            payload = None
            while line := await asyncio.to_thread(process.stdout.readline):
                event = json.loads(line)
                if event["type"] == "progress":
                    yield event
                elif event["type"] == "result":
                    payload = event["data"]
            await asyncio.to_thread(process.wait)
            stderr = await stderr_task
            if process.returncode or payload is None:
                logging.getLogger(__name__).error("Electrical QA worker failed: %s", stderr.decode("utf-8", errors="replace"))
                raise RuntimeError("전기도면 QA 실행에 실패했습니다. 서버의 전기도면 설정과 모델 연결을 확인해 주세요.")
            if not payload.get("ok"):
                logging.getLogger(__name__).error("Electrical QA verification failed: %s", payload)
                if "최종 도면 근거 검증 실패:" in str(payload.get("error", "")):
                    raise RuntimeError("도면 답변을 한 차례 교정했지만 근거 검증을 통과하지 못했습니다. 확인되지 않은 설명이 포함되어 답변을 제공하지 않았습니다.")
                raise RuntimeError("전기도면 근거 검증 또는 모델 호출에 실패했습니다. 서버의 QA 로그를 확인해 주세요.")
            yield {"type": "result", "data": payload["result"]}
    except asyncio.TimeoutError as exc:
        raise RuntimeError("전기도면 QA 제한시간(30분)을 초과했습니다.") from exc
    finally:
        if process.poll() is None:
            process.kill()
            await asyncio.to_thread(process.wait)
        await asyncio.gather(stderr_task, return_exceptions=True)
        for stream in (process.stdin, process.stdout, process.stderr):
            stream.close()
