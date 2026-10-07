"""Case-level parsing and Chroma/BM25 indexing for the shared build pipeline."""
import hashlib
import json
from pathlib import Path
import re
import pickle
from copy import deepcopy

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BUNDLE_NAME = "repairHistory_bm25_bundle.pkl"


def normalize(value):
    return re.sub(r"[^a-z0-9가-힣#]", "", str(value).lower())


def load_workbook(workbook, factory_id):
    import xlrd

    workbook = Path(workbook)
    book = xlrd.open_workbook(workbook, formatting_info=True)
    cases = []
    for sheet in book.sheets():
        if sheet.nrows < 3:
            continue
        headers = {normalize(v): i for i, v in enumerate(sheet.row_values(2)) if str(v).strip()}
        if not {"발생내용", "조치내용"} <= headers.keys():
            continue
        merged = {(r, c): (r0, c0) for r0, r1, c0, c1 in sheet.merged_cells
                  for r in range(r0, r1) for c in range(c0, c1)}
        for row in range(3, sheet.nrows):
            def cell(key):
                col = headers.get(key)
                if col is None:
                    return ""
                item = sheet.cell(*merged.get((row, col), (row, col)))
                if item.ctype == xlrd.XL_CELL_DATE:
                    return xlrd.xldate_as_datetime(item.value, book.datemode).isoformat(sep=" ")
                return str(item.value).strip()

            if not any(str(sheet.cell_value(row, headers[key])).strip() for key in ("발생내용", "조치내용")):
                continue
            if cell("순번") == "계" or "G0900" in cell("순번"):
                continue
            if normalize(cell("발생내용")) == "발생내용" and normalize(cell("조치내용")) == "조치내용":
                continue
            fields = {label: cell(key) for label, key in [
                ("발생일자(원본)", "발생일자"), ("결함개소", "결함개소"),
                ("발생내용", "발생내용"), ("조치내용", "조치내용"),
                ("조치일(원본)", "조치일"), ("미가동시간", "미가동시간h"),
                ("수리비용", "수리비용")]}
            meta = {"source_kind": "repairHistory", "case_type": "factory_history",
                    "factory_id": factory_id, "company": "연암" if factory_id == "yunam" else factory_id, "machine_name": sheet.name,
                    "source_doc_name": workbook.name, "sheet_name": sheet.name, "source_row": row + 1}
            content = f"출처: {meta['company']} 공장 수리 이력 / {sheet.name} 시트 / {row + 1}행\n장비: {sheet.name}\n"
            content += "\n".join(f"{k}: {v or '기록 없음'}" for k, v in fields.items())
            cases.append({"id": f"xls:{workbook.name}:{sheet.name}:{row + 1}", "document": content, "metadata": meta})
    return cases


def load_tacit(tacit):
    tacit = Path(tacit)
    cases = []
    for line_no, line in enumerate(tacit.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        match = re.match(r"업체명:\s*(.*?), 기계명:\s*(.*?), CNC:", line)
        if not match:
            raise ValueError(f"Unrecognized maintenance record at line {line_no}")
        meta = {"source_kind": "repairHistory", "case_type": "company_knowledge",
                "factory_id": "shared", "company": match[1], "machine_name": match[2],
                "source_doc_name": tacit.name, "source_row": line_no}
        cases.append({"id": f"txt:{tacit.name}:{line_no}", "document": f"출처: 업체별 수리 암묵지 / {line_no}줄\n{line}", "metadata": meta})
    return cases


def store_config(config, *, search=False):
    """Resolve existing relative config paths against their original working directory."""
    config = deepcopy(config)
    base = ROOT / ("backend" if search else "pipeline")
    for store in config.vector_db.stores.values():
        path = Path(store.search_path if search else store.db_path)
        store.db_path = str((base / path).resolve())
    return config


def build_index(cases, config, reset=False):
    from pipeline.ingestion.vector_writer import create_vector_collection, write_chroma, write_bm25

    config = store_config(config)
    name = config.id + "_repairHistory"
    bundle_path = Path(config.vector_db.get_db_path("bm25")) / BUNDLE_NAME
    # Reject wrong-factory data before touching either index.
    if any(c["metadata"]["factory_id"] not in {config.id, "shared"} for c in cases):
        raise ValueError("수리 이력의 공장과 빌드 설정이 다릅니다.")
    if len({c["id"] for c in cases}) != len(cases):
        raise ValueError("수리 사례 ID가 중복되었습니다.")
    collection = create_vector_collection(config, collection_name=name)
    fingerprint = hashlib.sha256(json.dumps([config.embedding.model, cases], ensure_ascii=False,
                                           sort_keys=True).encode()).hexdigest()
    saved = collection.metadata or {}
    if saved.get("model") not in (None, config.embedding.model) and not reset:
        raise ValueError("임베딩 모델이 변경되었습니다. --maintenance-only --reset으로 다시 빌드하세요.")
    if reset:
        import chromadb
        client = chromadb.PersistentClient(path=config.vector_db.get_db_path("chroma"))
        client.delete_collection(name)
        collection = create_vector_collection(config, collection_name=name)
    collection.modify(metadata={"status": "building",
                                "model": config.embedding.model, "fingerprint": fingerprint})
    existing = collection.get(include=["documents", "metadatas"])
    previous = {key: (doc, meta) for key, doc, meta in zip(
        existing["ids"], existing["documents"], existing["metadatas"])}
    chunks = [{"id": c["id"], "page_content": c["document"], "metadata": c["metadata"]} for c in cases]
    changed = [c for c in chunks if previous.get(c["id"]) != ("passage: " + c["page_content"], c["metadata"])]
    metadata_only = [c for c in changed if c["id"] in previous
                     and previous[c["id"]][0] == "passage: " + c["page_content"]]
    for offset in range(0, len(metadata_only), 500):
        batch = metadata_only[offset:offset + 500]
        collection.update(ids=[c["id"] for c in batch], metadatas=[c["metadata"] for c in batch])
    metadata_ids = {c["id"] for c in metadata_only}
    pending = [c for c in changed if c["id"] not in metadata_ids]
    write_chroma(collection, pending, config.id, config.vector_db.get_db_path("chroma"),
                 upsert=True, batch_size=16)
    stale = sorted(set(previous) - {c["id"] for c in cases})
    for offset in range(0, len(stale), 500):
        collection.delete(ids=stale[offset:offset + 500])
    write_bm25(config, chunks, output=str(bundle_path),
               extra_meta={"collection": name, "fingerprint": fingerprint})
    collection.modify(metadata={**collection.metadata, "status": "ready", "count": len(cases)})
    print(f"[{config.id}] 수리 사례 Chroma + BM25: {len(cases)}건", flush=True)


def build_sources(config, workbook=None, tacit=None, reset=False):
    """Explicit files, or all files in the factory/shared input folders."""
    workbooks = [Path(workbook)] if workbook else sorted((ROOT / "pipeline/data" / config.id / "repairHistory/inputs").glob("*.xls"))
    tacits = [Path(tacit)] if tacit else sorted((ROOT / "pipeline/data/shared/knowledge/inputs").glob("*.txt"))
    if not workbooks and not tacits:
        print("[수리 사례] 입력 파일이 없어 생략합니다.")
        return
    cases = [c for path in workbooks for c in load_workbook(path, config.id)]
    cases.extend(c for path in tacits for c in load_tacit(path))
    build_index(cases, config, reset=reset)


def search(question, config, machine_name="", top_k=6, balance_sources=False):
    import chromadb
    from backend.app.embeddings import load_embeddings
    from backend.app.core.bm25_tokenizer import tokenize_for_bm25

    config = store_config(config, search=True)
    with (Path(config.vector_db.get_db_path("bm25")) / BUNDLE_NAME).open("rb") as stream:
        bundle = pickle.load(stream)
    client = chromadb.PersistentClient(path=config.vector_db.get_db_path("chroma"))
    collection = client.get_collection(config.id + "_repairHistory", embedding_function=None)
    meta = collection.metadata or {}
    if (meta.get("status") != "ready" or meta.get("fingerprint") != bundle["meta"].get("fingerprint")
            or meta.get("count") != collection.count() or collection.count() != len(bundle["ids"])):
        raise ValueError("수리 이력 색인이 미완료 상태입니다. 빌드를 완료하세요.")
    if meta.get("model") != config.embedding.model:
        raise ValueError("수리 사례 임베딩 모델이 현재 설정과 다릅니다.")
    if not bundle["ids"]:
        return []
    query = np.asarray(load_embeddings(config)(["query: " + question])[0], dtype=np.float32)
    keywords = bundle["bm25"].get_scores(tokenize_for_bm25(question))
    pools = ("factory_history", "company_knowledge") if balance_sources else (None,)
    results = []
    for kind in pools:
        pool = [i for i, m in enumerate(bundle["metadatas"])
                if m["factory_id"] in {config.id, "shared"} and (kind is None or m["case_type"] == kind)]
        if not pool:
            continue
        candidate_k = min(len(pool), max(top_k * 4, 30))
        where = {"factory_id": {"$in": [config.id, "shared"]}}
        if kind:
            where = {"$and": [where, {"case_type": kind}]}
        vector = collection.query(query_embeddings=[query.tolist()], n_results=candidate_k,
                                  where=where, include=["distances"])
        vector_ids = vector["ids"][0]
        keyword_ids = [bundle["ids"][i] for i in sorted(pool, key=lambda i: -keywords[i])[:candidate_k]
                       if keywords[i] > 0]
        ranks = {}
        for order in (vector_ids, keyword_ids):
            for rank, key in enumerate(order, 1):
                ranks[key] = ranks.get(key, 0) + 1 / (60 + rank)
        candidates = collection.get(ids=list(ranks), include=["documents", "metadatas", "embeddings"])
        selected = []
        for key, document, metadata, embedding in zip(candidates["ids"], candidates["documents"],
                                                      candidates["metadatas"], candidates["embeddings"]):
            similarity = float(np.dot(query, embedding) / (np.linalg.norm(query) * np.linalg.norm(embedding)))
            if similarity < 0.60:
                continue
            same = bool(machine_name) and metadata["factory_id"] == config.id and normalize(metadata["machine_name"]) == normalize(machine_name)
            selected.append({"id": key, "document": document.removeprefix("passage: "),
                             "metadata": {**metadata, "same_machine": same}, "similarity": similarity,
                             "rrf_score": ranks[key] + (0.005 if same else 0)})
        selected.sort(key=lambda r: -r["rrf_score"])
        results.extend(selected[:top_k // 2 if balance_sources else top_k])
    # Do not return evidence if a build started while the query was running.
    current = client.get_collection(config.id + "_repairHistory").metadata or {}
    if current.get("status") != "ready" or current.get("fingerprint") != meta["fingerprint"]:
        raise ValueError("수리 사례가 갱신 중입니다. 다시 조회하세요.")
    return results
