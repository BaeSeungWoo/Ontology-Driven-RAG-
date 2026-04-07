# tests/unit/test_retriever.py
# conftest.py에서 미설치 패키지를 sys.modules mock 처리

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document


def make_doc(content, source, score, image_path=None):
    metadata = {"source": source}
    if image_path:
        metadata["image_path"] = image_path
    return (Document(page_content=content, metadata=metadata), score)


@pytest.fixture
def retriever(ollama_config):
    with patch("app.core.retriever.OllamaEmbeddings") as MockEmbed, \
         patch("app.core.retriever.Chroma") as MockChroma:
        mock_db = MagicMock()
        MockChroma.return_value = mock_db
        from app.core.retriever import KnowledgeRetriever
        r = KnowledgeRetriever(ollama_config)
        r._mock_db = mock_db
        yield r


class TestGetContextBaseMode:
    def test_base_mode_returns_empty(self, retriever):
        context, imgs, chunk_map = retriever.get_context("query", "base")
        assert context == ""
        assert imgs == []
        assert chunk_map == {}

    def test_base_mode_does_not_call_similarity_search(self, retriever):
        retriever.get_context("query", "base")
        retriever._mock_db.similarity_search_with_score.assert_not_called()


class TestGetContextRAGMode:
    def test_rag_mode_calls_similarity_search(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = []
        retriever.get_context("query", "rag")
        retriever._mock_db.similarity_search_with_score.assert_called_once_with("query", k=3)

    def test_filters_docs_below_threshold(self, retriever):
        # score_threshold=0.7, score=0.5 → 제외
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("내용", "test.pdf", 0.5)
        ]
        context, imgs, chunk_map = retriever.get_context("query", "rag")
        assert context == ""
        assert chunk_map == {}

    def test_includes_docs_above_threshold(self, retriever):
        # score_threshold=0.7, score=0.85 → 포함
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("중요한 내용", "test.pdf", 0.85)
        ]
        context, imgs, chunk_map = retriever.get_context("query", "rag")
        assert "중요한 내용" in context
        assert "test.pdf" in chunk_map

    def test_multiple_docs_joined_with_double_newline(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("내용1", "a.pdf", 0.9),
            make_doc("내용2", "b.pdf", 0.8),
        ]
        context, _, _ = retriever.get_context("query", "rag")
        assert "\n\n" in context

    def test_collects_image_paths(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("내용", "test.pdf", 0.9, image_path="/imgs/img1.png")
        ]
        _, imgs, _ = retriever.get_context("query", "rag")
        assert "/imgs/img1.png" in imgs

    def test_skips_image_if_no_metadata(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("내용", "test.pdf", 0.9)
        ]
        _, imgs, _ = retriever.get_context("query", "rag")
        assert imgs == []

    def test_chunk_map_keyed_by_source(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("문서 내용", "manual.pdf", 0.9)
        ]
        _, _, chunk_map = retriever.get_context("query", "rag")
        assert "manual.pdf" in chunk_map
        assert chunk_map["manual.pdf"] == "문서 내용"


class TestGetContextGraphMode:
    def test_graph_mode_appends_graph_text(self, retriever):
        retriever._mock_db.similarity_search_with_score.return_value = [
            make_doc("내용", "test.pdf", 0.9)
        ]
        context, _, _ = retriever.get_context("query", "graph")
        assert "[관계 정보]" in context

    def test_graph_context_stub_returns_expected_string(self, retriever):
        result = retriever._get_graph_context("query")
        assert "Graph DB" in result or "관계 정보" in result
