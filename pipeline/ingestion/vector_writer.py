from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import numpy as np
import torch

import chromadb
import faiss
from rank_bm25 import BM25Okapi

from backend.app.core.bm25_tokenizer import TOKENIZER_VERSION, tokenize_for_bm25
from backend.app.core.llm_handler import BaseLLM
from backend.app.embeddings import load_embeddings, ColpaliEmbedder
from backend.app.factories.config import Config

from pipeline.ingestion.openie_extractor import extract_triples_batch
import pipeline.ingestion.kg_utils as kg_mod

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

def write_chroma(collection, chunks: list[dict[str, Any]], id: str, db_path: str):
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
def write_bm25(config: Config, chunks: list[dict[str, Any]], output: str | None = None):
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
def write_faiss(config: Config, chunks: list[dict[str, Any]], db_path: str):
    faiss_path = Path(db_path)
    faiss_path.mkdir(parents=True, exist_ok=True)

    index_save_path = faiss_path / "faiss.index"
    parquet_save_path = faiss_path / "chunks.parquet"

    if not chunks:
        print("no chunks to index")
        return

    chunks_df = pd.DataFrame(chunks)

    def _build_passage(chunk: dict[str, Any]) -> str:
        metadata = chunk.get("metadata") or {}
        section_title = str(metadata.get("section_title") or "").strip()
        page_content = str(chunk.get("page_content") or "").strip()

        if section_title:
            return f"passage: {section_title}\n{page_content}"
        return f"passage: {page_content}"

    passages = [_build_passage(chunk) for chunk in chunks]

    embedding = load_embeddings(config)
    raw_embs = embedding(passages)
    embs = np.array(raw_embs).astype('float32')
    faiss.normalize_L2(embs)

    idx = faiss.IndexFlatIP(embs.shape[1])

    idx.add(embs)
    faiss.write_index(idx, str(index_save_path))
    print(f"faiss index saved: {index_save_path}")

    chunks_df.to_parquet(parquet_save_path, index=False)
    print(f"parquet saved: {parquet_save_path}")

# ──────────────────────────────────────────────────────────────────────────────
#  KG 관련
# ──────────────────────────────────────────────────────────────────────────────
def write_kg(config: Config, chunks: list[dict[str, Any]], db_path: str, llm: BaseLLM):
    if not chunks:
        print("no chunks to kg")
        return

    chunk_df = pd.DataFrame(chunks)

    kg_path = Path(db_path)
    kg_path.mkdir(parents=True, exist_ok=True)

    json_path = kg_path / "openie_results.jsonl"
    pkl_path = kg_path / "kg.pkl"

    def _build_pair(chunk: dict[str, Any]) -> tuple:
        metadata = chunk.get("metadata") or {}
        chunk_id = str(metadata.get("chunk_id") or "").strip()
        page_content = str(chunk.get("page_content") or "").strip()

        return (chunk_id, page_content)

    pairs = [_build_pair(r) for _, r in chunk_df.iterrows()]
    results = extract_triples_batch(llm=llm, chunks=pairs, stream_path=str(json_path))

    chunk_records = []
    for chunk in chunks:
        meta = chunk.get("metadata") or {}
        chunk_records.append({
            "chunk_id": str(meta.get("chunk_id") or "").strip(),
            "section_title": str(meta.get("section_title") or "").strip(),
            "doc_name": str(meta.get("source_doc_name") or "").strip(),
            "page_range": str(meta.get("page_range") or "").strip(),
            "text": str(chunk.get("page_content") or "").strip(),
        })
    g, entity_list = kg_mod.build_kg_openie(chunk_records, results)

    if not entity_list:
        print("추출된 entity list 없음, 빈 kg 저장")
        bundle = {
            "g": g,
            "entity_list": [],
            "entity_embs": np.zeros((0, 0), dtype=np.float32),
            "triple_embs": np.zeros((0, 0), dtype=np.float32),
            "edge_to_row": {},
        }
        with open(str(pkl_path), "wb") as f:
            pickle.dump(bundle, f)
        return

    embedding = load_embeddings(config)
    raw_embs = embedding(entity_list)
    ent_embs = np.array(raw_embs).astype('float32')
    faiss.normalize_L2(ent_embs)

    kg_mod.add_synonym_edges(g, entity_list, ent_embs)
    edges = [(u, v, k, d) for u, v, k, d in g.edges(keys=True, data=True)
             if d.get("predicate") not in ("appears_in", "synonym")]
    edge_keys = [(u, v, k) for u, v, k, _ in edges]
    triple_texts = [" ".join(d.get("surface") or (u, d.get("predicate", ""), v)) for u, v, _k, d in edges]

    if triple_texts:
        raw_tri_embs = embedding(triple_texts)
        tri_embs = np.asarray(raw_tri_embs, dtype=np.float32)
        faiss.normalize_L2(tri_embs)
    else:
        tri_embs = np.zeros((0, ent_embs.shape[1]), dtype=np.float32)

    bundle = {"g": g, "entity_list": entity_list, "entity_embs": ent_embs,
              "triple_embs": tri_embs, "edge_to_row": {ek: i for i, ek in enumerate(edge_keys)}}
    with open(str(pkl_path), "wb") as f:
        pickle.dump(bundle, f)

# ──────────────────────────────────────────────────────────────────────────────
#  멀티모달 관련
# ──────────────────────────────────────────────────────────────────────────────
def write_multimodal(
    chunks: list[dict[str, Any]],
    db_path: str | Path,
    embedding: ColpaliEmbedder,
    batch_size: int = 2
):
    mm_path = Path(db_path)
    mm_path.mkdir(parents=True, exist_ok=True)

    emb_path = mm_path / "img_emb.pt"
    meta_path = mm_path / "img_meta.parquet"

    if not chunks:
        print("no page images for multimodal index")
        return

    image_paths = [row["image_path"] for row in chunks]
    image_embs = embedding.embed_images(image_paths, batch_size=batch_size)

    rows: list[dict[str, Any]] = []
    for row, emb in zip(chunks, image_embs):
        item = dict(row)
        item["n_patches"] = int(emb.shape[0])
        rows.append(item)

    torch.save(image_embs, emb_path)
    pd.DataFrame(rows).to_parquet(meta_path, index=False)

    print(f"multimodal embeddings saved: {emb_path}")
    print(f"multimodal metadata saved: {meta_path}")
    print(f"multimodal indexed pages: {len(rows)}")