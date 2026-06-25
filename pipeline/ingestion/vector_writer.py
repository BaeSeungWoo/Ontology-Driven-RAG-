from __future__ import annotations

from typing import Any

import chromadb

from backend.app.embeddings import load_embeddings
from backend.app.factories.config import Config

BATCH_SIZE = 500

def create_vector_collection(config: Config) -> chromadb.Collection:
    vectordb_client = chromadb.PersistentClient(path=config.vector_db.db_path)
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