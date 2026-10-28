"""Readiness follows the persisted search data used by the chat backend."""
from functools import lru_cache
import logging
import json
import os
from pathlib import Path
import pickle
import subprocess
import sys
import hashlib
import tempfile
from time import monotonic

from fastapi import HTTPException

from app.core.electrical_qa import PACKAGE, SUPPORTED_MACHINES, config_for_machine, DISABLED_MESSAGE
from pipeline.ingestion.machine_resolver import machine_documents

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=8)
def _bm25_groups(bm25_path, revision):
    # Chroma initialization can change its file stamps without changing BM25.
    with Path(bm25_path).open("rb") as stream:
        bundle = pickle.load(stream)
    if bundle.get("bm25") is None:
        return {}
    groups = {}
    for chunk_id, meta, text in zip(bundle["ids"], bundle["metadatas"], bundle["documents"]):
        if not meta or not text or not text.removeprefix("passage: ").strip():
            continue
        source, kind = meta.get("source_doc_name"), meta.get("container_type", "")
        codes = meta.get("machine_code", [])
        if isinstance(codes, str):
            codes = [codes]
        if source:
            for code in codes:
                groups.setdefault((code, source, kind), []).append(chunk_id)
    return groups


def _matches_record(meta, text, key):
    code, source, kind = key
    meta = meta or {}
    codes = meta.get("machine_code", [])
    codes = [codes] if isinstance(codes, str) else codes
    return (code in codes and source == meta.get("source_doc_name") and kind == meta.get("container_type", "")
            and bool(text and text.removeprefix("passage: ").strip()))


@lru_cache(maxsize=8)
def _search_records(chroma_path, collection_name, bm25_path, revision):
    # Cache compact metadata until persisted search files change.
    if not (Path(chroma_path) / "chroma.sqlite3").is_file() or not Path(bm25_path).is_file():
        return ()
    # Persist only the validated summary, never a machine list or user permissions.
    key = json.dumps([chroma_path, collection_name, bm25_path])
    cache_path = ROOT / "backend/data/machine_readiness" / (hashlib.sha256(key.encode()).hexdigest() + ".json")
    fingerprint = json.dumps(revision)
    try:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached["version"] == 1 and cached["revision"] == fingerprint:
            return tuple(tuple(row) for row in cached["records"])
    except (OSError, ValueError, KeyError, TypeError):
        pass
    import chromadb
    stamp = Path(bm25_path).stat()
    groups = _bm25_groups(bm25_path, (stamp.st_mtime_ns, stamp.st_size))
    if not groups:
        return ()
    collection = chromadb.PersistentClient(path=chroma_path).get_collection(collection_name, embedding_function=None)
    # One representative per group, deduplicated for documents shared by machines.
    representatives = list(dict.fromkeys(ids[0] for ids in groups.values()))
    samples = {}
    for start in range(0, len(representatives), 500):
        batch = collection.get(ids=representatives[start:start + 500], include=["metadatas", "documents"])
        samples.update({ident: (meta, text) for ident, meta, text in
                        zip(batch["ids"], batch["metadatas"], batch["documents"])})
    records = set()
    for key, ids in groups.items():
        if _matches_record(*samples.get(ids[0], (None, None)), key):
            records.add(key)
            continue
        # A deleted or changed representative must not hide surviving indexed chunks.
        batch = collection.get(ids=ids, limit=1, include=["metadatas", "documents"])
        for meta, text in zip(batch["metadatas"], batch["documents"]):
            if _matches_record(meta, text, key):
                records.add(key)
    result = tuple(records)
    temporary = None
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=cache_path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "revision": fingerprint, "records": result}, stream)
        temporary.replace(cache_path)
    except OSError:
        logging.getLogger(__name__).warning("Could not cache machine readiness", exc_info=True)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


@lru_cache(maxsize=2)
def _electrical_ready(config_path, revision):
    # Reuse the drawing engine's own PDF/index/evidence validation, without LLM calls.
    result = subprocess.run(
        [sys.executable, str(PACKAGE / "qa_portable.py"), "--config", config_path, "--check"],
        cwd=PACKAGE, capture_output=True, timeout=15,
        **({"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}),
    )
    return result.returncode == 0


def machine_readiness(config, machines):
    revision = int(monotonic() // 15)
    chroma_path = Path(config.vector_db.get_search_path("chroma")).resolve()
    bm25_path = (Path(config.vector_db.get_search_path("bm25")) / "bm25_bundle.pkl").resolve()
    try:
        stamps = tuple((path.stat().st_mtime_ns, path.stat().st_size) if path.exists() else None
                       for path in (chroma_path / "chroma.sqlite3", chroma_path / "chroma.sqlite3-wal", bm25_path))
        records = _search_records(
            str(chroma_path), config.vector_db.collection_name or config.id, str(bm25_path), stamps,
        )
        search_error = False
    except Exception:
        logging.getLogger(__name__).exception("Machine search readiness check failed")
        records, search_error = (), True
    try:
        from app.core.ladder_linker import LadderLinker
        ladder_ready = bool(LadderLinker(ROOT / "pipeline" / "data" / config.id / "ladder" / "struct").blocks)
    except (OSError, ValueError, KeyError, TypeError):
        ladder_ready = False
    electrical_states = {}
    for code in (SUPPORTED_MACHINES & machines.keys()) if config.id == "yunam_origin" else ():
        try:
            config_path = config_for_machine(code)
            if isinstance(machines[code].get("document"), dict):
                drawing = Path(json.loads(config_path.read_text(encoding="utf-8-sig"))["pdf"]).stem
                if drawing not in {Path(name).stem for name in machine_documents(machines[code], "electrical")}:
                    continue
            electrical_states[code] = _electrical_ready(str(config_path), revision)
        except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
            electrical_states[code] = False
    result = {}
    for code, info in machines.items():
        documents = set(machine_documents(info, "manual"))
        ladder_documents = set(machine_documents(info, "ladder"))
        matched = set()
        has_ladder = False
        for indexed_code, source, kind in records:
            if indexed_code != code:
                continue
            # Same document-name matching rule as pipeline.ingestion.machine_resolver.
            if kind == "ladder":
                has_ladder |= any(source in doc or doc in source for doc in ladder_documents)
            else:
                matched.update(doc for doc in documents if source in doc or doc in source)
        state = ("no_documents" if not documents else "check_failed" if search_error else
                 "no_search_data" if not matched else "partial" if len(matched) < len(documents) else "ready")
        result[code] = {
            "readiness": state, "searchable_document_count": len(matched), "document_count": len(documents),
            "has_ladder": has_ladder and ladder_ready,
            "has_electrical": electrical_states.get(code, False),
        }
    return result


def require_machine_ready(code, config, machines, mode=None, persona=None):
    if config.id != "yunam_origin" and (mode == "electrical" or persona == "engineer"):
        raise HTTPException(409, DISABLED_MESSAGE)
    if config.id != "yunam_origin" and (persona not in (None, "operator") or mode not in (None, "rag", "manual")):
        raise HTTPException(409, "연암(기존)을 제외한 공장에서는 현장작업자·RAG만 사용할 수 있습니다.")
    if code == "ALL":
        raise HTTPException(409, "검색 가능한 장비를 선택해 주세요.")
    state = machine_readiness(config, machines).get(code, {})
    if mode == "electrical" or persona == "engineer":
        if not state.get("has_electrical"):
            raise HTTPException(409, "전기도면 데이터가 준비되지 않아 기술엔지니어 질의를 사용할 수 없습니다.")
        return
    if state.get("readiness") not in ("ready", "partial"):
        raise HTTPException(409, "검색 가능한 매뉴얼 데이터가 없어 준비 중인 장비입니다. 채팅을 사용할 수 없습니다.")
    if (mode == "ladder" or persona == "maintenance") and not state["has_ladder"]:
        raise HTTPException(409, "래더 데이터가 준비되지 않아 설비보전 질의를 사용할 수 없습니다.")
