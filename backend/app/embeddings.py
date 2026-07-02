# backend/app/embeddings.py
#
# 임베딩 함수 로딩 및 메타데이터 저장 유틸리티

import json
from pathlib import Path

from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from app.factories.config import Config

# ──────────────────────────────────────────────────────────────────────────────
#  chroma용 ollama 임베딩
# ──────────────────────────────────────────────────────────────────────────────
def load_embeddings(config: Config) -> OllamaEmbeddingFunction:
    """설정에서 OllamaEmbeddingFunction 인스턴스를 생성합니다."""
    return OllamaEmbeddingFunction(
        model_name=config.embedding.model,
        url=config.get_embedding_base_url()
    )

# ──────────────────────────────────────────────────────────────────────────────
#  embedding_metadata 저장
# ──────────────────────────────────────────────────────────────────────────────
def save_embedding_meta(config: Config) -> None:
    """임베딩 설정 메타데이터를 벡터 DB 경로에 저장합니다."""
    meta_path = Path(config.vector_db.get_db_path("chroma")) / "embedding_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "factory_id": config.id,
        "embedding_model": config.embedding.model,
        "embedding_base_url": config.get_embedding_base_url()
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
