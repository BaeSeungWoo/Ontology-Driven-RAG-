"""Synchronize the factory's manual collection and its derived search files."""
import json
from pathlib import Path
import sqlite3
from contextlib import closing

import faiss
import numpy as np
import pandas as pd

from backend.app.embeddings import load_embeddings, save_embedding_meta
from pipeline.build_machine_search import export_collection, source_revision
from pipeline.ingestion.prepared_documents import document_catalog, document_key
from pipeline.ingestion.vector_writer import (
    _build_passage, _embed_in_batches, create_vector_collection, write_bm25, write_chroma,
)


def sync_indexes(config, chunks, destination, *, skip_faiss=False):
    chroma = destination / "chroma"
    lexical = destination / "bm25"
    vectors = destination / "faiss"
    for folder in (chroma, lexical, vectors):
        folder.mkdir(parents=True, exist_ok=True)
    meta_path = chroma / "embedding_meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf8"))
        if (meta["factory_id"], meta["embedding_model"], meta["embedding_provider"]) != (
                config.id, config.embedding.model, config.embedding.provider):
            raise ValueError("기존 임베딩과 설정이 다릅니다. 별도 --output-root를 사용하세요.")
    collection = create_vector_collection(config, config.vector_db.collection_name)
    desired = {c["id"]: c for c in chunks}
    present = set()
    represented = {document_key(c["metadata"]["source_doc_name"]) for c in chunks}
    linked = document_catalog(config.machines)
    updates = []
    metadata = []
    stale = []
    for offset in range(0, collection.count(), 500):
        batch = collection.get(offset=offset, limit=500, include=["documents", "metadatas"])
        for ident, body, old in zip(batch["ids"], batch["documents"], batch["metadatas"]):
            source = document_key(old["source_doc_name"])
            if source in linked and source not in represented and linked[source]["document_type"] != "electrical":
                raise ValueError(f"기존 문서의 struct 누락: {source}")
            present.add(ident)
            row = desired.get(ident)
            if row is None:
                stale.append(ident)
            elif body != "passage: " + row["page_content"]:
                updates.append(row)
            elif old != row["metadata"]:
                metadata.append(row)
    updates.extend(row for ident, row in desired.items() if ident not in present)
    dirty = destination / ".manual-index-pending"
    changed = bool(updates or metadata or stale or dirty.exists())
    db = lexical / "machine_search.sqlite3"
    index_file = vectors / "faiss.index"
    rows_file = vectors / "chunks.parquet"
    faiss_pending = destination / ".faiss-sync-pending"
    if skip_faiss:
        print("FAISS 인덱스 생성 생략", flush=True)
        if changed and index_file.exists():
            faiss_pending.touch()
    elif changed or faiss_pending.exists() or not (index_file.is_file() and rows_file.is_file()):
        dirty.touch()
        sync_faiss(config, chunks, index_file, rows_file)
        faiss_pending.unlink(missing_ok=True)
    if changed or not (lexical / "bm25_bundle.pkl").is_file():
        dirty.touch()
        write_chroma(collection, updates, config.id, str(chroma), upsert=True)
        for i in range(0, len(metadata), 500):
            batch = metadata[i:i+500]
            collection.update(ids=[c["id"] for c in batch], metadatas=[c["metadata"] for c in batch])
        for i in range(0, len(stale), 500):
            collection.delete(ids=stale[i:i+500])
        bundle = lexical / "bm25_bundle.pending"
        write_bm25(config, chunks, output=str(bundle))
        bundle.replace(lexical / "bm25_bundle.pkl")
        save_embedding_meta(config)
    refresh = dirty.exists() or not db.is_file()
    if not refresh:
        with closing(sqlite3.connect(db)) as conn:
            info = dict(conn.execute("SELECT key,value FROM info"))
        refresh = info.get("source_revision") != json.dumps(source_revision(chroma, collection.name))
    if refresh:
        export_collection(collection, str(chroma), db)
    dirty.unlink(missing_ok=True)
    print(f"Chroma 본문 추가·변경 {len(updates)}, 장비 등 메타데이터 {len(metadata)}, 삭제 {len(stale)}")


def sync_faiss(config, chunks, index_file, rows_file):
    # Journal the pair: an interrupted rename must never associate vectors with old rows.
    pending = index_file.with_suffix(".pending")
    pending_rows = rows_file.with_suffix(".pending")
    commit = index_file.with_suffix(".commit")
    def publish():
        if pending.exists():
            pending.replace(index_file)
        if pending_rows.exists():
            pending_rows.replace(rows_file)
        commit.unlink()
    if commit.exists():
        publish()
    old_index = faiss.read_index(str(index_file)) if index_file.exists() and rows_file.exists() else None
    previous = {}
    if old_index is not None:
        frame = pd.read_parquet(rows_file)
        if old_index.ntotal != len(frame):
            raise ValueError("FAISS 벡터와 parquet 행 수가 다릅니다.")
        previous = {r["id"]: (i, _build_passage(r)) for i,r in enumerate(frame.to_dict("records"))}
    index = faiss.IndexFlatIP(old_index.d) if old_index is not None else None
    if old_index is not None and list(previous) == [row["id"] for row in chunks] and all(
            previous[row["id"]][1] == _build_passage(row) for row in chunks):
        pd.DataFrame(chunks, columns=["id", "page_content", "metadata"]).to_parquet(pending_rows, index=False)
        pending_rows.replace(rows_file)
        return
    embedding = None
    for offset in range(0, len(chunks), 128):
        rows = chunks[offset:offset+128]
        values = [None] * len(rows)
        missing, passages = [], []
        for pos, row in enumerate(rows):
            passage = _build_passage(row)
            old = previous.get(row["id"])
            if old is not None and old[1] == passage:
                values[pos] = old_index.reconstruct(old[0])
            else:
                missing.append(pos)
                passages.append(passage)
        if missing:
            if embedding is None:
                embedding = load_embeddings(config)
            for pos, vec in zip(missing, _embed_in_batches(embedding, passages, "FAISS")):
                values[pos] = vec
        batch = np.asarray(values, dtype=np.float32)
        if index is None or (index.ntotal == 0 and not previous):
            index = faiss.IndexFlatIP(batch.shape[1])
        index.add(batch)
    if index is None:
        index = faiss.IndexFlatIP(1)
    faiss.write_index(index, str(pending))
    pd.DataFrame(chunks, columns=["id","page_content","metadata"]).to_parquet(pending_rows, index=False)
    commit.touch()
    publish()
