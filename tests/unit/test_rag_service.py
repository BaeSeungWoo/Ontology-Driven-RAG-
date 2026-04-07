# tests/unit/test_rag_service.py

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


@pytest.fixture
def mock_service(ollama_config, registry_path):
    with patch("app.service.LLMProvider") as MockLLMProvider, \
         patch("app.service.KnowledgeRetriever") as MockRetriever, \
         patch("app.service.PromptManager") as MockPM, \
         patch("app.service.MemoryManager") as MockMM:

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock()
        MockLLMProvider.get_model.return_value = mock_llm

        mock_retriever = MagicMock()
        mock_retriever.get_context.return_value = ("검색된 컨텍스트", [], {"test.pdf": "내용"})
        MockRetriever.return_value = mock_retriever

        mock_pm = MagicMock()
        mock_pm.build.return_value = "조립된 프롬프트"
        MockPM.return_value = mock_pm

        mock_mm = MagicMock()
        mock_mm.get_history.return_value = ""
        MockMM.return_value = mock_mm

        from app.service import RAGService
        service = RAGService(ollama_config)
        service._mock_llm = mock_llm
        service._mock_retriever = mock_retriever
        service._mock_pm = mock_pm
        service._mock_mm = mock_mm
        yield service


class TestPrepareContext:
    @pytest.mark.asyncio
    async def test_calls_retriever_get_context(self, mock_service):
        await mock_service.prepare_context("질문", "rag")
        mock_service._mock_retriever.get_context.assert_called_once_with("질문", "rag")

    @pytest.mark.asyncio
    async def test_calls_prompt_manager_build(self, mock_service):
        await mock_service.prepare_context("질문", "rag")
        assert mock_service._mock_pm.build.called

    @pytest.mark.asyncio
    async def test_returns_three_tuple(self, mock_service):
        result = await mock_service.prepare_context("질문", "rag")
        assert isinstance(result, tuple)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_first_element_is_string(self, mock_service):
        full_prompt, imgs, chunk_map = await mock_service.prepare_context("질문", "rag")
        assert isinstance(full_prompt, str)

    @pytest.mark.asyncio
    async def test_passes_mode_to_retriever(self, mock_service):
        await mock_service.prepare_context("질문", "base")
        mock_service._mock_retriever.get_context.assert_called_once_with("질문", "base")


class TestAsk:
    @pytest.mark.asyncio
    async def test_loads_history_before_context(self, mock_service):
        call_order = []
        mock_service._mock_mm.get_history.side_effect = lambda *a: call_order.append("get_history") or ""
        mock_service._mock_retriever.get_context.side_effect = lambda *a: call_order.append("get_context") or ("", [], {})
        mock_service._mock_llm.ainvoke.return_value = MagicMock(content="답변")

        await mock_service.ask("session1", "질문", "rag")
        assert call_order.index("get_history") < call_order.index("get_context")

    @pytest.mark.asyncio
    async def test_base_mode_skips_retriever(self, mock_service):
        mock_service._mock_llm.ainvoke.return_value = MagicMock(content="답변")
        await mock_service.ask("s1", "질문", "base")
        mock_service._mock_retriever.get_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_rag_mode_calls_retriever(self, mock_service):
        mock_service._mock_llm.ainvoke.return_value = MagicMock(content="답변")
        await mock_service.ask("s1", "질문", "rag")
        mock_service._mock_retriever.get_context.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_to_memory_after_response(self, mock_service):
        mock_service._mock_llm.ainvoke.return_value = MagicMock(content="LLM 답변")
        await mock_service.ask("s1", "질문 내용", "rag")
        mock_service._mock_mm.save.assert_called_once_with("s1", "질문 내용", "LLM 답변")

    @pytest.mark.asyncio
    async def test_returns_response_content(self, mock_service):
        mock_service._mock_llm.ainvoke.return_value = MagicMock(content="정확한 답변")
        result = await mock_service.ask("s1", "질문", "rag")
        assert result == "정확한 답변"

    @pytest.mark.asyncio
    async def test_handles_response_without_content_attr(self, mock_service):
        mock_service._mock_llm.ainvoke.return_value = "직접 문자열 응답"
        result = await mock_service.ask("s1", "질문", "rag")
        assert result == "직접 문자열 응답"
