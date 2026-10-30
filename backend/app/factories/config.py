# backend/app/factories/config.py

from dataclasses import dataclass, field, replace
from typing import Dict, Optional
from pathlib import Path
import json
from .machines import load_machine_info


# ──────────────────────────────────────────────────────────────────────────────
#  LLM 설정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    provider: str                           # "openai" | "ollama" | "anthropic" | "google"
    model_name: str
    temperature: float = 0

    # Ollama / OpenAI 호환 서버(vLLM 등) 공용 — None 이면 각 핸들러의 기본값
    base_url: Optional[str] = None
    num_ctx: int = 8192                     # Ollama 전용

    # OpenAI / Anthropic / Google 전용. None 이면 환경변수에서 읽는다.
    api_key: Optional[str] = None

    # Anthropic / OpenAI 전용
    # max_tokens: int = 4096
    max_tokens: int = 1024

# ──────────────────────────────────────────────────────────────────────────────
#  임베딩 설정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EmbeddingConfig:
    model: str = "qwen3-embedding:8b"
    base_url: Optional[str] = None          # None이면 llm.base_url 공용
    provider: str = "ollama"

    def resolve_base_url(self, llm_base_url: Optional[str]) -> str:
        return self.base_url or llm_base_url or "http://localhost:11434"


# ──────────────────────────────────────────────────────────────────────────────
#  벡터 DB 설정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StorePathConfig:
    db_path: str
    search_path: str

@dataclass
class VectorDBConfig:
    collection_name: Optional[str] = None
    stores: dict[str, StorePathConfig] = field(
        default_factory=lambda: {
            "chroma": StorePathConfig(
                db_path="./data/chroma",
                search_path="../pipeline/data/chroma",
            )
        }
    )
    retrieval_k: int = 5
    score_threshold: float = 0.7
    chunk_size: int = 800
    chunk_overlap: int = 150

    def get_store(self, store_name: str) -> StorePathConfig:
        try:
            return self.stores[store_name]
        except KeyError as exc:
            available = ", ".join(sorted(self.stores))
            raise KeyError(f"Unknown store '{store_name}'. Available: {available}") from exc

    def get_db_path(self, store_name: str) -> str:
        return self.get_store(store_name).db_path

    def get_search_path(self, store_name: str) -> str:
        return self.get_store(store_name).search_path


# ──────────────────────────────────────────────────────────────────────────────
#  프롬프트 설정
#  - system_prompt: DB 조회 실패 시 최후 fallback 값만 보관
#  - 실제 system_prompt는 MS SQL PromptStore에서 factory_id 기준으로 조회
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class PromptConfig:
    default_prompt_id: str = "tech_expert"  # PromptStore 조회 시 기본 키
    fallback_system_prompt: str = "당신은 기술 전문가입니다."  # DB 조회 실패 시 사용


# ──────────────────────────────────────────────────────────────────────────────
#  최상위 통합 설정
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Config:
    id: str                                 # 공장 식별자 — URL /chat/{id} 와 일치
    llm: LLMConfig
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    vector_db: VectorDBConfig  = field(default_factory=VectorDBConfig)
    prompt: PromptConfig       = field(default_factory=PromptConfig)
    graph_db_url: Optional[str] = None
    machines: dict[str, dict] = field(default_factory=dict)

    def get_embedding_base_url(self) -> str:
        return self.embedding.resolve_base_url(self.llm.base_url)

# 모델 선택은 답변 생성에만 사용한다. 공장 데이터와 임베딩은 FACTORY_CONFIGS에서 관리한다.
# 기존 API와 대화 이력의 모델 키는 유지한다.
CONFIGS: Dict[str, Config] = {
    "ollama_config": Config(id="ollama_config", llm=LLMConfig(
            provider="ollama",
            # model_name="gpt-oss:20b",
            model_name="gemma4:31b",
            base_url="http://192.168.1.179:11434",
            temperature=0,
            num_ctx=8192,
            # num_ctx=16384,
            max_tokens=1024,
            # max_tokens=2049,
        )),
    "openai_config": Config(id="openai_config", llm=LLMConfig(
            provider="openai",
            model_name="gpt-4o",
            temperature=0,
            max_tokens=2048,
        )),
    "anthropic_config": Config(id="anthropic_config", llm=LLMConfig(
            provider="anthropic",
            model_name="claude-sonnet-4-6",
            temperature=0,
            max_tokens=1024,
        )),
    "google_config": Config(id="google_config", llm=LLMConfig(
            provider="google",
            model_name="gemini-2.0-flash",
            temperature=0,
            max_tokens=1024,
        )),
    "vllm_config": Config(id="vllm_config", llm=LLMConfig(
        provider="openai",
        model_name="Qwen3-VL",
        base_url="http://127.0.0.1:8100/v1",
        api_key="EMPTY",                    # vLLM 은 키를 검사하지 않지만 SDK 가 빈 값을 거부한다
        temperature=0,
        max_tokens=3072,                    # 서버 max_model_len 8192 = 프롬프트 + 응답
    )),
}

@dataclass
class FactoryConfig:
    embedding: EmbeddingConfig
    vector_db: VectorDBConfig
    prompt: PromptConfig
    default_model: str = "vllm_config"


FACTORY_CONFIGS: Dict[str, FactoryConfig] = {
    "yunam": FactoryConfig(
        embedding=EmbeddingConfig(model="qwen3-embedding:8b", base_url="http://127.0.0.1:8101/v1", provider="openai"),
        vector_db=VectorDBConfig(
            stores={
                "chroma": StorePathConfig(
                    db_path="./data/yunam/chroma",
                    search_path="../pipeline/data/yunam/chroma",
                ),
                "bm25": StorePathConfig(
                    db_path="./data/yunam/bm25",
                    search_path="../pipeline/data/yunam/bm25",
                ),
                "faiss": StorePathConfig(
                    db_path="./data/yunam/faiss",
                    search_path="../pipeline/data/yunam/faiss",
                ),
                "kg": StorePathConfig(
                    db_path="./data/yunam/kg",
                    search_path="../pipeline/data/yunam/kg",
                ),
                "multimodal": StorePathConfig(
                    db_path="./data/yunam/multimodal",
                    search_path="../pipeline/data/yunam/multimodal",
                ),
            },
            retrieval_k=3,
            score_threshold=0.8,
        ),
        prompt=PromptConfig(
            default_prompt_id="tech_expert",
            fallback_system_prompt="당신은 연암 공장의 설비 유지보수 전문가입니다.",
        ),
    ),
    "yulkok": FactoryConfig(
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            base_url="http://127.0.0.1:8101/v1",
            provider="openai",
        ),
        vector_db=VectorDBConfig(
            stores={
                "chroma": StorePathConfig(
                    db_path="./data/yulkok/chroma",
                    search_path="../pipeline/data/yulkok/chroma",
                ),
                "bm25": StorePathConfig(
                    db_path="./data/yulkok/bm25",
                    search_path="../pipeline/data/yulkok/bm25",
                ),
                "faiss": StorePathConfig(
                    db_path="./data/yulkok/faiss",
                    search_path="../pipeline/data/yulkok/faiss",
                ),
                "kg": StorePathConfig(
                    db_path="./data/yulkok/kg",
                    search_path="../pipeline/data/yulkok/kg",
                ),
                "multimodal": StorePathConfig(
                    db_path="./data/yulkok/multimodal",
                    search_path="../pipeline/data/yulkok/multimodal",
                ),
            },
            retrieval_k=7,
            score_threshold=0.6,
        ),
        prompt=PromptConfig(
            default_prompt_id="tech_expert",
            fallback_system_prompt="당신은 율곡 공장의 정밀 공정 분석가입니다.",
        ),
    ),
    "poongsan": FactoryConfig(
        embedding=EmbeddingConfig(model="qwen3-embedding:8b", base_url="http://127.0.0.1:8101/v1", provider="openai"),
        vector_db=VectorDBConfig(
            stores={
                "chroma": StorePathConfig(
                    db_path="./data/poongsan/chroma",
                    search_path="../pipeline/data/poongsan/chroma",
                ),
                "bm25": StorePathConfig(
                    db_path="./data/poongsan/bm25",
                    search_path="../pipeline/data/poongsan/bm25",
                ),
                "faiss": StorePathConfig(
                    db_path="./data/poongsan/faiss",
                    search_path="../pipeline/data/poongsan/faiss",
                ),
                "kg": StorePathConfig(
                    db_path="./data/poongsan/kg",
                    search_path="../pipeline/data/poongsan/kg",
                ),
                "multimodal": StorePathConfig(
                    db_path="./data/poongsan/multimodal",
                    search_path="../pipeline/data/poongsan/multimodal",
                ),
            },
            retrieval_k=5,
            score_threshold=0.75,
        ),
        prompt=PromptConfig(
            default_prompt_id="tech_expert",
            fallback_system_prompt="당신은 풍산 공장의 품질 관리 전문가입니다.",
        ),
    ),
}
FACTORY_CONFIGS["yunam_origin"] = replace(
    FACTORY_CONFIGS["yunam"],
    embedding=EmbeddingConfig(model="qwen3-embedding:8b", base_url="http://192.168.1.179:11434"),
)


def get_factory_config(model_key: str, factory_id: str = "yunam") -> Config:
    from fastapi import HTTPException
    if factory_id not in FACTORY_CONFIGS:
        raise HTTPException(400, "등록되지 않은 공장입니다.")
    if model_key not in CONFIGS:
        raise HTTPException(404, "해당 모델 설정을 찾을 수 없습니다.")
    factory = FACTORY_CONFIGS[factory_id]
    model = CONFIGS[model_key]
    embedding = factory.embedding
    root = Path(__file__).resolve().parents[3]
    stores = {name: StorePathConfig(
        db_path=str(root / "backend" / "data" / factory_id / name),
        search_path=str(root / "pipeline" / "data" / factory_id / name),
    ) for name in factory.vector_db.stores}
    settings_path = root / "pipeline/data" / factory_id / "build_info/search_settings.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    if settings and (settings["site_id"] != factory_id or settings["embedding_model"] != embedding.model):
        raise ValueError("공장 검색 인덱스와 임베딩 설정이 일치하지 않습니다.")
    collection_name = "yunam" if factory_id == "yunam_origin" else factory_id
    return Config(id=factory_id, llm=model.llm, embedding=embedding, prompt=factory.prompt,
                   vector_db=replace(factory.vector_db, stores=stores, collection_name=settings.get("collection", collection_name)),
                   machines=load_machine_info(factory_id=factory_id))
