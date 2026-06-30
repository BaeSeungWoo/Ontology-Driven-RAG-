from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import numpy as np
import pandas as pd

import chromadb
import faiss
from rank_bm25 import BM25Okapi

from backend.app.core.bm25_tokenizer import TOKENIZER_VERSION, tokenize_for_bm25
from backend.app.embeddings import load_embeddings, load_colpali_embeddings, encode
from backend.app.factories.config import Config

BATCH_SIZE = 500

# ──────────────────────────────────────────────────────────────────────────────
#  Chroma 관련
# ──────────────────────────────────────────────────────────────────────────────
def create_vector_collection(config: Config) -> chromadb.Collection:
    vectordb_client = chromadb.PersistentClient(
        path=config.vector_db.get_db_path("chroma")
    )
    embedding = load_embeddings(config)

    return vectordb_client.get_or_create_collection(
        name=config.id,
        embedding_function=embedding,
        metadata={"hnsw:space": "cosine"}
    )

def upsert(collection, chunks: list[dict[str, Any]], id: str, db_path: str):
    if not chunks:
        print(f"[{id}] 저장할 청크 데이터가 없습니다")
        return
    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i: i+BATCH_SIZE]

        # 핵심 수정: documents 리스트를 만들 때 "passage: " 접두사를 추가합니다.
        processed_documents = [f"passage: {doc['page_content']}" for doc in batch]

        collection.add(
            ids=[doc["id"] for doc in batch],
            documents=processed_documents,  # 접두사가 붙은 텍스트 전달
            metadatas=[doc["metadata"] for doc in batch]
        )
        print(f"  - 진행률: {min(i + BATCH_SIZE, len(chunks))}/{len(chunks)}")
    # ids = [c.metadata["chunk_id"] for c in chunks]
    # db.add_documents(documents=chunks, ids=ids)
    print(f"[{id}] 저장 완료 → {db_path}")

# ──────────────────────────────────────────────────────────────────────────────
#  BM25 관련
# ──────────────────────────────────────────────────────────────────────────────
def write_bm25_bundle(config: Config, chunks: list[dict[str, Any]], output: str | None = None):
    documents = [f"passage: {chunk['page_content']}" for chunk in chunks]
    tokenized = [tokenize_for_bm25(chunk["page_content"]) for chunk in chunks]
    bm25 = BM25Okapi(tokenized)

    out_path = Path(output) if output else Path(config.vector_db.get_db_path("bm25")) / "bm25_bundle.pkl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = {
        "collection": config.id,
        "chunk_count": len(chunks),
        "embedding_model": config.embedding.model,
        "tokenizer": TOKENIZER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    bundle = {
        "bm25": bm25,
        "ids": [chunk["id"] for chunk in chunks],
        "documents": documents,
        "metadatas": [chunk["metadata"] for chunk in chunks],
        "meta": meta,
    }

    with out_path.open("wb") as f:
        pickle.dump(bundle, f)

    with out_path.with_suffix(".meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[{config.id}] BM25 bundle saved: {out_path}")

# ──────────────────────────────────────────────────────────────────────────────
#  FAISS 관련
# ──────────────────────────────────────────────────────────────────────────────

def indexing_and_save_parquet(config: Config, chunks: list[dict[str, Any]]):
    embedding = load_colpali_embeddings(config)
    chunks_df = pd.DataFrame(chunks)

    def _build_passage(chunk: dict[str, Any]) -> str:
        metadata = chunk.get("metadata") or {}
        section_title = str(metadata.get("section_title") or "").strip()
        page_content = str(chunk.get("page_content") or "").strip()

        if section_title:
            return f"passage: {section_title}\n{page_content}"
        return f"passage: {page_content}"

    passages = [_build_passage(chunk) for chunk in chunks]

    embs = None
    if not passages:
        embs = np.zeros((0, embedding.get_sentence_embedding_dimension()), dtype=np.float32)
    else:
        with torch.inference_mode():
            embs = embedding.encode(
                passages,
                batch_size=BATCH_SIZE,
                show_progress_bar=len(passages) > 256,
                convert_to_numpy=True,
                normalize_embeddings=True,
            ).astype(np.float32)

    idx = faiss.IndexFlatIP(embs.shape[1])
    idx.add(embs)

    faiss_path = Path(config.vector_db.get_db_path("faiss"))
    faiss_path.mkdir(parents=True, exist_ok=True)
    index_save_path = faiss_path / "faiss.index"
    parquet_save_path = faiss_path / "chunks.parquet"

    faiss.write_index(idx, str(index_save_path))
    print(f"[{config.id}] faiss index saved: {index_save_path}")
    
    chunks_df.to_parquet(parquet_save_path, index=False)
    print(f"[{config.id}] parquet saved: {parquet_save_path}")

# ──────────────────────────────────────────────────────────────────────────────
#  KG 관련
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
#  멀티모달 관련
# ──────────────────────────────────────────────────────────────────────────────
