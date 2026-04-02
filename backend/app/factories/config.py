# backend/app/factories/config.py

from dataclasses import dataclass, field
from typing import Dict, Optional


# ──────────────────────────────────────────────────────────────────────────────
#  LLM 설정
# ──────────────────────────────────────────────────────────────────────────────
 
@dataclass
class LLMConfig:
    provider: str               # "openai" | "ollama" | "anthropic"
    model_name: str
    base_url: Optional[str] = None          # Ollama 전용
    temperature: float = 0
    num_ctx: int = 8192                     # Ollama 컨텍스트 길이
    api_key: Optional[str] = None           # 미설정 시 환경변수 자동 사용

# ──────────────────────────────────────────────────────────────────────────────
#  임베딩 설정
# ──────────────────────────────────────────────────────────────────────────────
 
@dataclass
class EmbeddingConfig:
    model: str = "qwen3-embedding:8b"
    base_url: Optional[str] = None          # 미설정 시 LLMConfig.base_url 공용
 
    def resolve_base_url(self, llm_base_url: Optional[str]) -> str:
        """임베딩 전용 URL이 없으면 LLM 서버 URL을 공용으로 사용합니다."""
        return self.base_url or llm_base_url or "http://localhost:11434"
    
# ──────────────────────────────────────────────────────────────────────────────
#  벡터 DB 설정
# ──────────────────────────────────────────────────────────────────────────────
 
@dataclass
class VectorDBConfig:
    db_path: str = "./data/chroma"
    retrieval_k: int = 5                    # 검색 문서 수
    score_threshold: float = 0.7            # 유사도 필터 기준
    chunk_size: int = 800
    chunk_overlap: int = 150

# ──────────────────────────────────────────────────────────────────────────────
#  프롬프트 · 페르소나 설정
# ──────────────────────────────────────────────────────────────────────────────
 
@dataclass
class PromptConfig:
    system_prompt: str = "당신은 기술 전문가입니다."
    prompt_id: str = "tech_expert"
 
# ──────────────────────────────────────────────────────────────────────────────
#  최상위 통합 설정
# ──────────────────────────────────────────────────────────────────────────────
 
@dataclass
class Config:
    id: str
    llm: LLMConfig
    embedding: EmbeddingConfig  = field(default_factory=EmbeddingConfig)
    vector_db: VectorDBConfig   = field(default_factory=VectorDBConfig)
    prompt: PromptConfig        = field(default_factory=PromptConfig)
    graph_db_url: Optional[str] = None      # Neo4j 등 Graph DB URL
 
    def get_embedding_base_url(self) -> str:
        return self.embedding.resolve_base_url(self.llm.base_url)

# ──────────────────────────────────────────────────────────────────────────────
#  인스턴스 등록
#  항목 추가 시 CONFIGS 딕셔너리에만 추가하면 됩니다.
# ──────────────────────────────────────────────────────────────────────────────
 
CONFIGS: Dict[str, Config] = {
    "ollama_config": Config(
        id="A",
        llm=LLMConfig(
            provider="ollama",
            model_name="gpt-oss:20b",
            base_url="http://192.168.1.179:11434",
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            # base_url 생략 → llm.base_url 공용
        ),
        vector_db=VectorDBConfig(
            db_path="./data/A/chroma",
            retrieval_k=3,
            score_threshold=0.8,
        ),
        prompt=PromptConfig(
            system_prompt="당신은 A의 설비 유지보수 전문가입니다.",
            prompt_id="maintenance_expert",
        ),
    ),
    "openai_config": Config(
        id="B",
        llm=LLMConfig(
            provider="openai",
            model_name="gpt-4o",
        ),
        embedding=EmbeddingConfig(
            model="qwen3-embedding:8b",
            base_url="http://192.168.1.180:11434",  # 별도 임베딩 서버
        ),
        vector_db=VectorDBConfig(
            db_path="./data/B/chroma",
            retrieval_k=7,
            score_threshold=0.6,
        ),
        prompt=PromptConfig(
            system_prompt="당신은 B의 정밀 공정 분석가입니다.",
            prompt_id="process_analyst",
        ),
    ),
    # "C": Config(...)
}