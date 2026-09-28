# backend/app/factories/config.py

from dataclasses import dataclass, field, replace
from typing import Dict, Optional
import json
from pathlib import Path


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

MACHINE_INFO_PATH = Path(__file__).resolve().parent / "machine_info.json"
with MACHINE_INFO_PATH.open("r", encoding="utf-8-sig") as f:
    machine_info = json.load(f)

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

# ──────────────────────────────────────────────────────────────────────────────
#  인스턴스 등록
#  - key: 프론트엔드 드롭다운 표시 및 /chat/{key} 라우팅에 사용
#  - 새 공장 추가 시 CONFIGS에만 항목 추가
# ──────────────────────────────────────────────────────────────────────────────

CONFIGS: Dict[str, Config] = {

    # ── A 공장 : Ollama 로컬 모델 ─────────────────────────────────────────────
    "ollama_config": Config(
        id="yunam",
        llm=LLMConfig(
            provider="ollama",
            # model_name="gpt-oss:20b",
            model_name="gemma4:31b",
            base_url="http://192.168.1.179:11434",
            temperature=0,
            num_ctx=8192,
            # num_ctx=16384,
            max_tokens=1024,
            # max_tokens=2049,
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
        ),
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
        machines=machine_info
    ),

    # ── B 공장 : OpenAI ───────────────────────────────────────────────────────
    "openai_config": Config(
        id="yulkok",
        llm=LLMConfig(
            provider="openai",
            model_name="gpt-4o",
            temperature=0,
            max_tokens=2048,
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            base_url="http://192.168.1.180:11434",
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
        machines=machine_info
    ),

    # ── C 공장 : Anthropic ────────────────────────────────────────────────────
    "anthropic_config": Config(
        id="poongsan",
        llm=LLMConfig(
            provider="anthropic",
            model_name="claude-sonnet-4-6",
            temperature=0,
            max_tokens=1024,
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            base_url="http://192.168.1.180:11434",
        ),
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
        machines=machine_info
    ),

    # ── D 공장 : Google Gemini ────────────────────────────────────────────────
    "google_config": Config(
        id="D",
        llm=LLMConfig(
            provider="google",
            model_name="gemini-2.0-flash",
            temperature=0,
            max_tokens=1024,
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            base_url="http://192.168.1.180:11434",
        ),
        vector_db=VectorDBConfig(
            stores={
                "chroma": StorePathConfig(
                    db_path="./data/D/chroma",
                    search_path="../pipeline/data/D/chroma",
                ),
                "bm25": StorePathConfig(
                    db_path="./data/D/bm25",
                    search_path="../pipeline/data/D/bm25",
                ),
                "faiss": StorePathConfig(
                    db_path="./data/D/faiss",
                    search_path="../pipeline/data/D/faiss",
                ),
                "kg": StorePathConfig(
                    db_path="./data/D/kg",
                    search_path="../pipeline/data/D/kg",
                ),
                "multimodal": StorePathConfig(
                    db_path="./data/D/multimodal",
                    search_path="../pipeline/data/D/multimodal",
                ),
            },
            retrieval_k=5,
            score_threshold=0.7,
        ),
        prompt=PromptConfig(
            default_prompt_id="tech_expert",
            fallback_system_prompt="당신은 D 공장의 자동화 설비 전문가입니다.",
        ),
        machines=machine_info
    ),
}


# ── 로컬 vLLM : A 공장(yunam) 데이터 그대로 두고 LLM 만 교체 ──────────────────
#   vLLM 이 OpenAI 호환 API 를 제공하므로 provider 는 "openai" 를 쓴다.
#   서버: python -m vllm.entrypoints.openai.api_server --served-model-name Qwen3-VL
#   원격(로컬 PC)에서 쓸 때는 SSH 터널을 로컬 8100 으로 연다 (8000 은 백엔드가 사용).
#     ssh -p 10521 -N -L 8100:127.0.0.1:8000 -L 8101:127.0.0.1:8001 work@max.gntp.or.kr
CONFIGS["vllm_config"] = replace(
    CONFIGS["ollama_config"],
    llm=LLMConfig(
        provider="openai",
        model_name="Qwen3-VL",
        base_url="http://127.0.0.1:8100/v1",
        api_key="EMPTY",                    # vLLM 은 키를 검사하지 않지만 SDK 가 빈 값을 거부한다
        temperature=0,
        max_tokens=1024,                    # 서버 max_model_len 8192 = 프롬프트 + 응답
    ),
    # 임베딩은 LLM 과 별개다. 명시하지 않으면 llm.base_url(vLLM)을 그대로 물려받아
    # Ollama 임베딩 요청이 vLLM 으로 가버리므로 반드시 따로 지정한다.
    embedding=EmbeddingConfig(
        model="qwen3-embedding:8b",
        base_url="http://192.168.1.179:11434",
    ),
)
