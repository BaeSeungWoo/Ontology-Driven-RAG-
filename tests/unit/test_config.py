# tests/unit/test_config.py

import pytest
from app.factories.config import (
    Config, LLMConfig, EmbeddingConfig, VectorDBConfig, PromptConfig, CONFIGS
)


class TestLLMConfig:
    def test_defaults(self):
        cfg = LLMConfig(provider="ollama", model_name="llama3")
        assert cfg.temperature == 0
        assert cfg.num_ctx == 8192
        assert cfg.base_url is None
        assert cfg.api_key is None

    def test_explicit_values(self):
        cfg = LLMConfig(
            provider="openai",
            model_name="gpt-4o",
            temperature=0.5,
            api_key="sk-test",
        )
        assert cfg.temperature == 0.5
        assert cfg.api_key == "sk-test"


class TestEmbeddingConfig:
    def test_resolve_uses_own_url(self):
        cfg = EmbeddingConfig(base_url="http://embed-server:11434")
        assert cfg.resolve_base_url("http://llm-server:11434") == "http://embed-server:11434"

    def test_resolve_falls_back_to_llm_url(self):
        cfg = EmbeddingConfig()
        assert cfg.resolve_base_url("http://llm-server:11434") == "http://llm-server:11434"

    def test_resolve_falls_back_to_localhost(self):
        cfg = EmbeddingConfig()
        assert cfg.resolve_base_url(None) == "http://localhost:11434"

    def test_default_model(self):
        cfg = EmbeddingConfig()
        assert cfg.model == "qwen3-embedding:8b"


class TestVectorDBConfig:
    def test_defaults(self):
        cfg = VectorDBConfig()
        assert cfg.chunk_size == 800
        assert cfg.chunk_overlap == 150
        assert cfg.retrieval_k == 5
        assert cfg.score_threshold == 0.7
        assert cfg.db_path == "./data/chroma"


class TestConfig:
    def test_get_embedding_base_url_delegates(self, ollama_config):
        # ollama_config has embedding.base_url=None, llm.base_url="http://localhost:11434"
        result = ollama_config.get_embedding_base_url()
        assert result == "http://localhost:11434"

    def test_get_embedding_base_url_uses_embedding_url(self):
        cfg = Config(
            id="X",
            llm=LLMConfig(provider="ollama", model_name="m", base_url="http://llm:11434"),
            embedding=EmbeddingConfig(base_url="http://embed:11434"),
        )
        assert cfg.get_embedding_base_url() == "http://embed:11434"

    def test_graph_db_url_defaults_to_none(self, ollama_config):
        assert ollama_config.graph_db_url is None


class TestCONFIGS:
    def test_has_expected_keys(self):
        assert "ollama_config" in CONFIGS
        assert "openai_config" in CONFIGS

    def test_all_values_are_config_instances(self):
        for key, val in CONFIGS.items():
            assert isinstance(val, Config), f"{key} is not a Config instance"

    def test_ollama_config_provider(self):
        assert CONFIGS["ollama_config"].llm.provider == "ollama"

    def test_openai_config_provider(self):
        assert CONFIGS["openai_config"].llm.provider == "openai"
