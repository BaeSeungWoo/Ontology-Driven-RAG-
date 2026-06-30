from __future__ import annotations

import json
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rank_bm25 import BM25Okapi

from backend.app.core.bm25_tokenizer import TOKENIZER_VERSION, tokenize_for_bm25


def write_bm25_bundle(config: Any, chunks: list[dict[str, Any]], output: str | None = None) -> Path:
    documents = [f"passage: {chunk['page_content']}" for chunk in chunks]
    tokenized = [tokenize_for_bm25(chunk["page_content"]) for chunk in chunks]
    bm25 = BM25Okapi(tokenized)

    out_path = Path(output) if output else Path(config.vector_db.db_path).parent / "bm25" / "bm25_bundle.pkl"
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
    return out_path
