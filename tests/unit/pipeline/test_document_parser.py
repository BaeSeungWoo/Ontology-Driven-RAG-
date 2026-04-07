# tests/unit/pipeline/test_document_parser.py

import re
import pytest
from langchain_core.documents import Document
from pipeline.data_loader import DocumentParser


@pytest.fixture
def parser():
    return DocumentParser(chunk_size=100, chunk_overlap=20)


class TestDocumentParserSplit:
    def test_returns_list_of_documents(self, parser, sample_docs):
        result = parser.split(sample_docs)
        assert isinstance(result, list)
        assert all(isinstance(d, Document) for d in result)

    def test_assigns_chunk_id_to_metadata(self, parser, sample_docs):
        result = parser.split(sample_docs)
        for chunk in result:
            assert "chunk_id" in chunk.metadata

    def test_chunk_id_is_12_char_hex_string(self, parser, sample_docs):
        result = parser.split(sample_docs)
        for chunk in result:
            assert re.fullmatch(r"[0-9a-f]{12}", chunk.metadata["chunk_id"])

    def test_chunk_id_is_deterministic(self, parser):
        doc = Document(page_content="결정적 내용입니다.", metadata={"source": "test.pdf"})
        result1 = parser.split([doc])
        result2 = parser.split([doc])
        ids1 = [c.metadata["chunk_id"] for c in result1]
        ids2 = [c.metadata["chunk_id"] for c in result2]
        assert ids1 == ids2

    def test_chunk_id_differs_for_different_content(self, parser):
        doc1 = Document(page_content="내용 A입니다.", metadata={})
        doc2 = Document(page_content="내용 B입니다.", metadata={})
        res1 = parser.split([doc1])
        res2 = parser.split([doc2])
        assert res1[0].metadata["chunk_id"] != res2[0].metadata["chunk_id"]

    def test_preserves_source_metadata(self, parser):
        doc = Document(page_content="테스트 내용", metadata={"source": "manual.pdf"})
        result = parser.split([doc])
        for chunk in result:
            assert chunk.metadata["source"] == "manual.pdf"

    def test_empty_docs_returns_empty_list(self, parser):
        result = parser.split([])
        assert result == []

    def test_single_small_doc_returns_one_chunk(self, parser):
        doc = Document(page_content="짧은 내용", metadata={})
        result = parser.split([doc])
        assert len(result) == 1

    def test_large_doc_splits_into_multiple_chunks(self):
        # chunk_size=50으로 작게 설정
        small_parser = DocumentParser(chunk_size=50, chunk_overlap=5)
        long_content = "가나다라마바사아자차카타파하 " * 20  # 충분히 긴 내용
        doc = Document(page_content=long_content, metadata={})
        result = small_parser.split([doc])
        assert len(result) > 1
