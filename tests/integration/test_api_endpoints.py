# tests/integration/test_api_endpoints.py

import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def mock_rag_service():
    service = MagicMock()
    service.prepare_context = AsyncMock(
        return_value=("테스트 프롬프트", [], {"test.pdf": "내용"})
    )

    async def mock_astream(prompt):
        for token in ["안녕", "하세요"]:
            yield MagicMock(content=token)

    service.llm.astream = mock_astream
    return service


@pytest.fixture
def client(mock_rag_service):
    with patch("app.service.LLMProvider"), \
         patch("app.service.KnowledgeRetriever"), \
         patch("app.service.PromptManager"), \
         patch("app.service.MemoryManager"):
        from app.main import app
        with patch("app.main.services", {"ollama_config": mock_rag_service}):
            with TestClient(app) as c:
                yield c


VALID_BODY = {
    "session_id": "test-session",
    "question": "테스트 질문입니다.",
    "mode": "rag",
}


class TestChatEndpointBasic:
    def test_valid_request_returns_200(self, client):
        response = client.post("/chat/ollama_config", json=VALID_BODY)
        assert response.status_code == 200

    def test_unknown_factory_returns_404(self, client):
        response = client.post("/chat/nonexistent_factory", json=VALID_BODY)
        assert response.status_code == 404

    def test_404_response_has_detail_message(self, client):
        response = client.post("/chat/nonexistent_factory", json=VALID_BODY)
        assert "detail" in response.json()

    def test_response_is_streaming(self, client):
        response = client.post("/chat/ollama_config", json=VALID_BODY)
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type


class TestChatEndpointStreaming:
    def test_metadata_line_sent_first(self, client):
        response = client.post("/chat/ollama_config", json=VALID_BODY)
        first_line = response.text.split("\n")[0]
        assert first_line.startswith("METADATA:")

    def test_metadata_is_valid_json(self, client):
        response = client.post("/chat/ollama_config", json=VALID_BODY)
        first_line = response.text.split("\n")[0]
        metadata_str = first_line[len("METADATA:"):]
        metadata = json.loads(metadata_str)
        assert "images" in metadata
        assert "sources" in metadata


class TestChatEndpointValidation:
    def test_missing_session_id_returns_422(self, client):
        body = {"question": "질문"}
        response = client.post("/chat/ollama_config", json=body)
        assert response.status_code == 422

    def test_missing_question_returns_422(self, client):
        body = {"session_id": "s1"}
        response = client.post("/chat/ollama_config", json=body)
        assert response.status_code == 422

    def test_default_mode_is_rag(self, client, mock_rag_service):
        body = {"session_id": "s1", "question": "Q"}
        client.post("/chat/ollama_config", json=body)
        call_args = mock_rag_service.prepare_context.call_args
        # mode 인자 확인
        assert call_args.args[1] == "rag" or call_args.kwargs.get("mode") == "rag"
