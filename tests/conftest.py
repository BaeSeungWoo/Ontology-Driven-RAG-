# tests/conftest.py
#
# 공유 픽스처 및 sys.path 설정

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# backend/app 및 pipeline 임포트 경로 설정
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
sys.path.insert(0, str(Path(__file__).parent.parent))

# 미설치 외부 패키지를 sys.modules로 사전 mock 처리
_OPTIONAL_MODULES = [
    "langchain_openai",
    "langchain_anthropic",
    "docling",
    "docling.document_converter",
    "fitz",       # PyMuPDF (설치되지 않은 경우 mock)
]
for _mod in _OPTIONAL_MODULES:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

import pytest
from langchain_core.documents import Document


# ── Config 픽스처 ─────────────────────────────────────────────────────────────

@pytest.fixture
def ollama_config():
    from app.factories.config import Config, LLMConfig, EmbeddingConfig, VectorDBConfig, PromptConfig
    return Config(
        id="TEST",
        llm=LLMConfig(
            provider="ollama",
            model_name="test-model",
            base_url="http://localhost:11434",
        ),
        embedding=EmbeddingConfig(model="test-embed"),
        vector_db=VectorDBConfig(
            db_path="./test_data/chroma",
            retrieval_k=3,
            score_threshold=0.7,
        ),
        prompt=PromptConfig(
            system_prompt="당신은 테스트 전문가입니다.",
            prompt_id="tech_expert",
        ),
    )


@pytest.fixture
def openai_config():
    from app.factories.config import Config, LLMConfig, EmbeddingConfig, VectorDBConfig, PromptConfig
    return Config(
        id="TEST_OAI",
        llm=LLMConfig(
            provider="openai",
            model_name="gpt-4o",
        ),
        embedding=EmbeddingConfig(
            model="test-embed",
            base_url="http://localhost:11434",
        ),
        vector_db=VectorDBConfig(db_path="./test_data/chroma_oai"),
        prompt=PromptConfig(system_prompt="You are a test assistant.", prompt_id="tech_expert"),
    )


@pytest.fixture
def anthropic_config():
    from app.factories.config import Config, LLMConfig, EmbeddingConfig, VectorDBConfig, PromptConfig
    return Config(
        id="TEST_ANT",
        llm=LLMConfig(
            provider="anthropic",
            model_name="claude-sonnet-4-6",
        ),
        embedding=EmbeddingConfig(
            model="test-embed",
            base_url="http://localhost:11434",
        ),
        vector_db=VectorDBConfig(db_path="./test_data/chroma_ant"),
        prompt=PromptConfig(system_prompt="You are a test assistant.", prompt_id="tech_expert"),
    )


# ── 레지스트리 픽스처 ─────────────────────────────────────────────────────────

SAMPLE_REGISTRY = {
    "tech_expert": {
        "persona": "당신은 기술 전문가입니다.",
        "guide": "정확하고 간결하게 답변하세요.",
    },
    "maintenance_expert": {
        "persona": "당신은 설비 유지보수 전문가입니다.",
        "guide": "안전 절차를 우선적으로 안내하세요.",
    },
}


@pytest.fixture
def registry_path(tmp_path):
    """실제 registry.json 파일을 tmp_path에 생성합니다."""
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(SAMPLE_REGISTRY, ensure_ascii=False), encoding="utf-8")
    return str(path)


# ── Document 픽스처 ───────────────────────────────────────────────────────────

@pytest.fixture
def sample_docs():
    return [
        Document(page_content="섹션 A 내용입니다.", metadata={"source": "test.pdf"}),
        Document(page_content="섹션 B 내용입니다.", metadata={"source": "test.pdf"}),
    ]


# ── Upstage API 응답 픽스처 ───────────────────────────────────────────────────

@pytest.fixture
def upstage_api_response():
    return {
        "elements": [
            {
                "content": {"markdown": "## 제목\n내용 텍스트"},
                "type": "heading",
                "page": 1,
                "confidence": 0.99,
            },
            {
                "content": {"markdown": "단락 텍스트입니다."},
                "type": "paragraph",
                "page": 1,
                "confidence": 0.95,
            },
            {
                "content": {"markdown": ""},   # 빈 element → 스킵 대상
                "type": "figure",
                "page": 2,
                "confidence": 0.8,
            },
        ]
    }
