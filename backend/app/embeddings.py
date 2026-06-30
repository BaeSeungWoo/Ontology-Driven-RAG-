# backend/app/embeddings.py
#
# 임베딩 함수 로딩 및 메타데이터 저장 유틸리티

import json
import torch
import numpy as np
from pathlib import Path

# from langchain_community.embeddings import OllamaEmbeddings
from chromadb.utils.embedding_functions import OllamaEmbeddingFunction
from sentence_transformers import SentenceTransformer
from app.factories.config import Config

# ──────────────────────────────────────────────────────────────────────────────
#  chroma용 ollama 임베딩
# ──────────────────────────────────────────────────────────────────────────────
def load_embeddings(config: Config) -> OllamaEmbeddingFunction:
    # """설정에서 OllamaEmbedding 인스턴스를 생성합니다."""

    # return OllamaEmbeddings(
    #     model=config.embedding.model,
    #     base_url=config.get_embedding_base_url(),
    # )
    """설정에서 OllamaEmbeddingFunction 인스턴스를 생성합니다."""
    return OllamaEmbeddingFunction(
        model_name=config.embedding.model,
        url=config.get_embedding_base_url()
    )

# ──────────────────────────────────────────────────────────────────────────────
#  colpali용 sentence_transformer 임베딩
# ──────────────────────────────────────────────────────────────────────────────
def load_colpali_embeddings(config: Config) -> SentenceTransformer:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name=config.embedding.colpali_model, device=device)
    model.max_seq_length = config.embedding.colpali_max_seq_length
    return model
    
def encode(embedding_model: SentenceTransformer, texts: list[str], batch_size: int = 32, normalize: bool = True) -> np.ndarray:
    if not texts:
        return np.zeros((0, embedding_model.get_sentence_embedding_dimension()), dtype=np.float32)
    with torch.inference_mode():
        embs = embedding_model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 256,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
        )
    return embs.astype(np.float32)

def unload(embedding_model):
    del embedding_model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
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
        "embedding_base_url": config.get_embedding_base_url(),
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
