# tests/unit/test_llm_handler.py
# conftest.py에서 langchain_openai, langchain_anthropic 등을 sys.modules mock 처리

import pytest
from unittest.mock import patch, MagicMock
from app.core.llm_handler import LLMProvider


class TestLLMProviderOpenAI:
    def test_get_model_returns_chatopenai(self, openai_config):
        with patch("app.core.llm_handler.ChatOpenAI") as MockChatOpenAI:
            MockChatOpenAI.return_value = MagicMock()
            model = LLMProvider.get_model(openai_config)
            assert MockChatOpenAI.called

    def test_get_model_openai_uses_correct_model_name(self, openai_config):
        with patch("app.core.llm_handler.ChatOpenAI") as MockChatOpenAI:
            LLMProvider.get_model(openai_config)
            call_kwargs = MockChatOpenAI.call_args.kwargs
            assert call_kwargs["model"] == "gpt-4o"

    def test_get_model_openai_streaming_true(self, openai_config):
        with patch("app.core.llm_handler.ChatOpenAI") as MockChatOpenAI:
            LLMProvider.get_model(openai_config)
            call_kwargs = MockChatOpenAI.call_args.kwargs
            assert call_kwargs["streaming"] is True

    def test_get_model_openai_temperature_zero(self, openai_config):
        with patch("app.core.llm_handler.ChatOpenAI") as MockChatOpenAI:
            LLMProvider.get_model(openai_config)
            call_kwargs = MockChatOpenAI.call_args.kwargs
            assert call_kwargs["temperature"] == 0

    def test_get_model_openai_reads_api_key_from_env(self, openai_config):
        with patch("app.core.llm_handler.ChatOpenAI") as MockChatOpenAI, \
             patch("os.getenv", return_value="sk-test-key") as mock_getenv:
            LLMProvider.get_model(openai_config)
            call_kwargs = MockChatOpenAI.call_args.kwargs
            assert call_kwargs["api_key"] == "sk-test-key"


class TestLLMProviderOllama:
    def test_get_model_returns_chatollama(self, ollama_config):
        with patch("app.core.llm_handler.ChatOllama") as MockChatOllama:
            MockChatOllama.return_value = MagicMock()
            LLMProvider.get_model(ollama_config)
            assert MockChatOllama.called

    def test_get_model_ollama_uses_correct_model_name(self, ollama_config):
        with patch("app.core.llm_handler.ChatOllama") as MockChatOllama:
            LLMProvider.get_model(ollama_config)
            call_kwargs = MockChatOllama.call_args.kwargs
            assert call_kwargs["model"] == "test-model"

    def test_get_model_ollama_uses_base_url(self, ollama_config):
        with patch("app.core.llm_handler.ChatOllama") as MockChatOllama:
            LLMProvider.get_model(ollama_config)
            call_kwargs = MockChatOllama.call_args.kwargs
            assert call_kwargs["base_url"] == "http://localhost:11434"

    def test_get_model_ollama_sets_num_ctx(self, ollama_config):
        with patch("app.core.llm_handler.ChatOllama") as MockChatOllama:
            LLMProvider.get_model(ollama_config)
            call_kwargs = MockChatOllama.call_args.kwargs
            assert call_kwargs["num_ctx"] == 8192


class TestLLMProviderAnthropic:
    def test_get_model_returns_chatanthropic(self, anthropic_config):
        with patch("app.core.llm_handler.ChatAnthropic") as MockChatAnthropic:
            MockChatAnthropic.return_value = MagicMock()
            LLMProvider.get_model(anthropic_config)
            assert MockChatAnthropic.called

    def test_get_model_anthropic_uses_correct_model_name(self, anthropic_config):
        with patch("app.core.llm_handler.ChatAnthropic") as MockChatAnthropic:
            LLMProvider.get_model(anthropic_config)
            call_kwargs = MockChatAnthropic.call_args.kwargs
            assert call_kwargs["model"] == "claude-sonnet-4-6"


class TestLLMProviderErrors:
    def test_unknown_provider_raises_valueerror(self, ollama_config):
        from app.factories.config import LLMConfig
        ollama_config.llm.provider = "unknown_provider"
        with pytest.raises(ValueError) as exc_info:
            LLMProvider.get_model(ollama_config)
        assert "unknown_provider" in str(exc_info.value)

    def test_valueerror_message_lists_allowed_values(self, ollama_config):
        ollama_config.llm.provider = "unknown_provider"
        with pytest.raises(ValueError) as exc_info:
            LLMProvider.get_model(ollama_config)
        error_msg = str(exc_info.value)
        assert "openai" in error_msg
        assert "ollama" in error_msg
        assert "anthropic" in error_msg
