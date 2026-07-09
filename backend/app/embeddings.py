# backend/app/embeddings.py
#
# 임베딩 함수 로딩 및 메타데이터 저장 유틸리티

import json
from pathlib import Path
from typing import Iterable

import torch
from PIL import Image

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
#  Colpali용 이미지 임베딩
# ──────────────────────────────────────────────────────────────────────────────
class ColpaliEmbedder:
    def __init__(
        self,
        model_name: str = "vidore/colqwen2-v1.0",
        fallback_name: str = "vidore/colpali-v1.3",
        device: str = None,
        dtype: str = "bfloat16", 
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        torch_dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}[dtype]
        self.model_name = None
        for name in (model_name, fallback_name):
            try:
                self._load(name, torch_dtype)
                self.model_name = name
                break
            except Exception as e:
                print(f"Colpali load failed for {name}: {type(e).__name__}: {e}")
        if self.model_name is None:
            raise RuntimeError("Failed to load any Colpali variant")
        print(f"ColpaliEncoder ready: {self.model_name} on {self.device}")

    def _load(self, name: str, torch_dtype):
        if "colqwen2" in name.lower():
            from colpali_engine.models import ColQwen2, ColQwen2Processor
            self.model = ColQwen2.from_pretrained(
                name, torch_dtype=torch_dtype, device_map=self.device
            ).eval()
            self.processor = ColQwen2Processor.from_pretrained(name)
        else:
            from colpali_engine.models import ColPali, ColPaliProcessor
            self.model = ColPali.from_pretrained(
                name, torch_dtype=torch_dtype, device_map=self.device
            ).eval()
            self.processor = ColPaliProcessor.from_pretrained(name)

    @torch.inference_mode()
    def embed_images(self, paths: Iterable[Path | str], batch_size: int = 4) -> list[torch.Tensor]:
        """Each image → tensor of shape (num_patches, 128). Returns a list,
        because patch counts may differ between images."""
        out: list[torch.Tensor] = []
        paths = list(paths)
        for i in range(0, len(paths), batch_size):
            batch = [Image.open(p).convert("RGB") for p in paths[i: i + batch_size]]
            inputs = self.processor.process_images(batch).to(self.device)
            embs = self.model(**inputs)  # (B, T, 128)
            for b in range(embs.shape[0]):
                out.append(embs[b].detach().to(torch.float16).cpu())
            for img in batch:
                img.close()
        return out

    @torch.inference_mode()
    def embed_query(self, query: str) -> torch.Tensor:
        """Query text → (num_tokens, 128)."""
        inputs = self.processor.process_queries([query]).to(self.device)
        embs = self.model(**inputs)  # (1, T, 128)
        return embs[0].detach().to(torch.float16).cpu()

    @torch.inference_mode()
    def score(self, query_emb: torch.Tensor, image_embs: list[torch.Tensor]) -> list[float]:
        """ColBERT max-sim score: for each query token, max over patch tokens,
        then sum over query tokens.
        """
        q = query_emb.float()
        scores: list[float] = []
        for img_emb in image_embs:
            ie = img_emb.float()
            # (T_q, T_img) cosine = q @ ie.T (already L2-normalized internally? colpali yes)
            sim = q @ ie.T
            s = sim.max(dim=1).values.sum().item()
            scores.append(s)
        return scores

    def unload(self):
        del self.model
        del self.processor
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
        "embedding_base_url": config.get_embedding_base_url()
    }
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
