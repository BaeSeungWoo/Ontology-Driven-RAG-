# tests/unit/pipeline/test_docling_parser.py
# conftest.py에서 docling을 sys.modules mock 처리

import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document
from pipeline.parsers.docling_parser import DoclingParser


class TestSplitByHeading:
    """_split_by_heading은 순수 정적 메서드 — 모킹 불필요."""

    def test_no_headings_returns_full_text_as_single_item(self):
        text = "헤딩 없는 일반 텍스트입니다.\n두 번째 줄입니다."
        result = DoclingParser._split_by_heading(text)
        assert result == [text]

    def test_single_heading_returns_two_parts(self):
        text = "도입부 내용\n## 섹션 1\n섹션 1 내용"
        result = DoclingParser._split_by_heading(text)
        assert len(result) == 2
        assert "도입부 내용" in result[0]
        assert "## 섹션 1" in result[1]

    def test_multiple_headings_splits_all(self):
        text = "도입\n## 섹션 A\n내용 A\n## 섹션 B\n내용 B\n## 섹션 C\n내용 C"
        result = DoclingParser._split_by_heading(text)
        assert len(result) == 4  # 도입 + 섹션A + 섹션B + 섹션C

    def test_preserves_heading_marker_in_section(self):
        text = "도입\n## 제목\n본문"
        result = DoclingParser._split_by_heading(text)
        assert result[1].startswith("## 제목")

    def test_ignores_h1_and_h3(self):
        text = "# H1 헤딩\n내용\n### H3 헤딩\n더 많은 내용"
        result = DoclingParser._split_by_heading(text)
        # ## 없으면 전체가 단일 항목
        assert result == [text]

    def test_empty_string_returns_single_empty_item(self):
        result = DoclingParser._split_by_heading("")
        assert result == [""]


class TestDoclingParserParse:
    @pytest.fixture
    def mock_converter(self):
        with patch("pipeline.parsers.docling_parser.DocumentConverter") as MockConverter:
            instance = MockConverter.return_value
            mock_result = MagicMock()
            mock_result.document.export_to_markdown.return_value = (
                "도입부\n## 섹션 1\n내용 1\n## 섹션 2\n내용 2"
            )
            instance.convert.return_value = mock_result
            yield instance

    def test_parse_returns_document_list(self, mock_converter):
        parser = DoclingParser()
        result = parser.parse("/data/manual.pdf")
        assert isinstance(result, list)
        assert all(isinstance(d, Document) for d in result)

    def test_parse_filters_empty_sections(self):
        with patch("pipeline.parsers.docling_parser.DocumentConverter") as MockConverter:
            instance = MockConverter.return_value
            mock_result = MagicMock()
            mock_result.document.export_to_markdown.return_value = (
                "도입부\n## 섹션 1\n\n   \n## 섹션 2\n실제 내용"
            )
            instance.convert.return_value = mock_result
            parser = DoclingParser()
            result = parser.parse("/data/manual.pdf")
        # 공백만 있는 섹션은 제외
        contents = [d.page_content for d in result]
        assert all(c.strip() for c in contents)

    def test_parse_sets_section_index_metadata(self, mock_converter):
        parser = DoclingParser()
        result = parser.parse("/data/manual.pdf")
        indices = [d.metadata["section_index"] for d in result]
        assert indices == list(range(len(result)))

    def test_parse_sets_source_to_filename(self, mock_converter):
        parser = DoclingParser()
        result = parser.parse("/data/manual.pdf")
        for doc in result:
            assert doc.metadata["source"] == "manual.pdf"

    def test_parse_sets_doc_type_to_manual(self, mock_converter):
        parser = DoclingParser()
        result = parser.parse("/data/manual.pdf")
        for doc in result:
            assert doc.metadata["doc_type"] == "manual"

    def test_parse_sets_parser_to_docling(self, mock_converter):
        parser = DoclingParser()
        result = parser.parse("/data/manual.pdf")
        for doc in result:
            assert doc.metadata["parser"] == "docling"
