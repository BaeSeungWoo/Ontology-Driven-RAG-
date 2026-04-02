# backend/app/embeddings.py
#
# 임베딩 함수 로딩 및 메타데이터 저장 유틸리티

import json
from pathlib import Path

from langchain_community.embeddings import OllamaEmbeddings

from app.factories.config import Config


def load_embeddings(config: Config) -> OllamaEmbeddings:
    """설정에서 OllamaEmbeddings 인스턴스를 생성합니다."""
    return OllamaEmbeddings(
        model=config.embedding.model,
        base_url=config.get_embedding_base_url(),
    )


def save_embedding_meta(config: Config) -> None:
    """임베딩 설정 메타데이터를 벡터 DB 경로에 저장합니다."""
    meta_path = Path(config.vector_db.db_path) / "embedding_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "factory_id": config.id,
        "embedding_model": config.embedding.model,
        "embedding_base_url": config.get_embedding_base_url(),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
