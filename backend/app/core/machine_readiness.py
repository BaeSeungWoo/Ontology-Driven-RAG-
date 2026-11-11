"""Readiness follows the persisted search data used by the chat backend."""
from functools import lru_cache
import logging
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic

from fastapi import HTTPException

from app.core.electrical_qa import package_for_factory, configs_for_machine
from pipeline.ingestion.machine_resolver import machine_documents
from pipeline.ingestion.prepared_documents import document_key

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=128)
def _electrical_ready(config_path, revision, factory_id):
    # Reuse the selected engine's PDF/index/evidence validation, without LLM calls.
    package = package_for_factory(factory_id)
    result = subprocess.run(
        [sys.executable, str(package / "qa_portable.py"), "--config", config_path, "--check"],
        cwd=package, capture_output=True, timeout=15,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    return result.returncode == 0


def machine_readiness(config, machines):
    revision = int(monotonic() // 15)
    try:
        from app.core.machine_search import MachineSearch
        search = MachineSearch(config)
        records = tuple(row for code in machines for row in search.records(code))
        search_error = False
    except Exception:
        logging.getLogger(__name__).exception("Machine search readiness check failed")
        records, search_error = (), True
    try:
        from app.core.ladder_linker import LadderLinker
        ladder_ready = any(machine_documents(info, "ladder") for info in machines.values()) and bool(
            LadderLinker(ROOT / "pipeline" / "data" / config.id / "ladder" / "struct").blocks)
    except (OSError, ValueError, KeyError, TypeError):
        ladder_ready = False
    electrical_states = {}
    for code, info in machines.items():
        if not machine_documents(info, "electrical"):
            continue
        try:
            paths = configs_for_machine(config.id, code)
            electrical_states[code] = False
            for path in paths:
                try:
                    if _electrical_ready(str(path), revision, config.id):
                        electrical_states[code] = True
                        break
                except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
                    continue
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            electrical_states[code] = False
    result = {}
    for code, info in machines.items():
        documents = set(machine_documents(info, "manual")) | set(machine_documents(info, "controller"))
        ladder_documents = set(machine_documents(info, "ladder"))
        matched = set()
        has_ladder = False
        for indexed_code, source, kind in records:
            if indexed_code != code:
                continue
            # Same document-name matching rule as pipeline.ingestion.machine_resolver.
            source_key = document_key(source)
            if kind == "ladder":
                has_ladder |= any(source_key in document_key(doc) or document_key(doc) in source_key for doc in ladder_documents)
            else:
                matched.update(doc for doc in documents if source_key in document_key(doc) or document_key(doc) in source_key)
        state = ("no_documents" if not documents else "check_failed" if search_error else
                 "no_search_data" if not matched else "partial" if len(matched) < len(documents) else "ready")
        result[code] = {
            "readiness": state, "searchable_document_count": len(matched), "document_count": len(documents),
            "has_ladder": has_ladder and ladder_ready,
            "has_electrical": electrical_states.get(code, False),
        }
    return result


def require_machine_ready(code, config, machines, mode=None, persona=None):
    allowed_modes = (None, "rag", "manual", "electrical")
    if persona == "operator" and config.id in ("yunam", "yulkok", "poongsan"):
        allowed_modes += ("repairHistory",)
    if config.id != "yunam_origin" and (persona not in (None, "operator", "engineer") or mode not in allowed_modes):
        raise HTTPException(409, "정비·보전·관리자 기능은 신규 공장 연결 준비 중입니다.")
    if code == "ALL":
        raise HTTPException(409, "검색 가능한 장비를 선택해 주세요.")
    if code not in machines:
        raise HTTPException(409, "등록되지 않은 장비입니다. 장비 목록을 새로 불러와 주세요.")
    state = machine_readiness(config, {code: machines[code]}).get(code, {})
    if mode == "electrical" or persona == "engineer":
        if not state.get("has_electrical"):
            raise HTTPException(409, "전기도면 데이터가 준비되지 않아 기술엔지니어 질의를 사용할 수 없습니다.")
        return
    if state.get("readiness") not in ("ready", "partial"):
        raise HTTPException(409, "검색 가능한 매뉴얼 데이터가 없어 준비 중인 장비입니다. 채팅을 사용할 수 없습니다.")
    if (mode == "ladder" or persona == "maintenance") and not state["has_ladder"]:
        raise HTTPException(409, "래더 데이터가 준비되지 않아 설비보전 질의를 사용할 수 없습니다.")
