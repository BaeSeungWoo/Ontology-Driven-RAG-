# tests/unit/pipeline/test_site_a_parser.py

import os
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document


@pytest.fixture(autouse=True)
def set_upstage_key():
    with patch.dict(os.environ, {"UPSTAGE_API_KEY": "test-key"}):
        yield


@pytest.fixture
def parser():
    with patch("pipeline.adapters.site_a.DoclingParser") as MockDocling, \
         patch("pipeline.adapters.site_a.UpstageParser") as MockUpstage:
        MockDocling.return_value = MagicMock()
        MockUpstage.return_value = MagicMock()
        from pipeline.adapters.site_a import SiteAParser
        p = SiteAParser()
        p._mock_docling = MockDocling.return_value
        p._mock_upstage = MockUpstage.return_value
        yield p


class TestExtractDrawingId:
    def test_found(self):
        from pipeline.adapters.site_a import SiteAParser
        result = SiteAParser._extract_drawing_id("도면 DWG-1234 참고하세요")
        assert result == "DWG-1234"

    def test_not_found(self):
        from pipeline.adapters.site_a import SiteAParser
        result = SiteAParser._extract_drawing_id("도면 번호 없음")
        assert result == ""

    def test_takes_first_match(self):
        from pipeline.adapters.site_a import SiteAParser
        result = SiteAParser._extract_drawing_id("DWG-1111 그리고 DWG-2222")
        assert result == "DWG-1111"

    def test_various_digit_lengths(self):
        from pipeline.adapters.site_a import SiteAParser
        assert SiteAParser._extract_drawing_id("DWG-99") == "DWG-99"
        assert SiteAParser._extract_drawing_id("DWG-123456") == "DWG-123456"


class TestParseManual:
    def test_delegates_to_docling(self, parser):
        parser._mock_docling.parse.return_value = [
            Document(page_content="내용", metadata={"source": "test.pdf", "doc_type": "manual"})
        ]
        parser.parse_manual("/data/manual.pdf")
        parser._mock_docling.parse.assert_called_once_with("/data/manual.pdf")

    def test_adds_site_a_metadata(self, parser):
        parser._mock_docling.parse.return_value = [
            Document(page_content="내용", metadata={"source": "test.pdf"})
        ]
        result = parser.parse_manual("/data/manual.pdf")
        for doc in result:
            assert doc.metadata["site"] == "A"

    def test_preserves_existing_metadata(self, parser):
        parser._mock_docling.parse.return_value = [
            Document(page_content="내용", metadata={"source": "test.pdf", "doc_type": "manual"})
        ]
        result = parser.parse_manual("/data/manual.pdf")
        assert result[0].metadata["doc_type"] == "manual"


class TestParseScanned:
    def test_delegates_to_upstage(self, parser):
        parser._mock_upstage.parse.return_value = [
            Document(page_content="OCR 내용", metadata={"source": "scan.pdf"})
        ]
        parser.parse_scanned("/data/scan.pdf")
        parser._mock_upstage.parse.assert_called_once_with("/data/scan.pdf")

    def test_adds_site_a_metadata(self, parser):
        parser._mock_upstage.parse.return_value = [
            Document(page_content="OCR 내용", metadata={"source": "scan.pdf"})
        ]
        result = parser.parse_scanned("/data/scan.pdf")
        for doc in result:
            assert doc.metadata["site"] == "A"


class TestParseDrawing:
    def _make_mock_page(self, text, images=None):
        page = MagicMock()
        page.get_text.return_value = text
        page.get_images.return_value = images or []
        return page

    def test_skips_empty_pages(self, parser):
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([
            self._make_mock_page(""),  # 빈 페이지 → 스킵
        ]))
        mock_pdf.__enter__ = MagicMock(return_value=mock_pdf)
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            result = parser.parse_drawing("/data/drawing.pdf")

        assert result == []

    def test_sets_page_number(self, parser):
        page1 = self._make_mock_page("도면 내용 1")
        page2 = self._make_mock_page("도면 내용 2")
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([page1, page2]))
        mock_pdf.close = MagicMock()

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            result = parser.parse_drawing("/data/drawing.pdf")

        pages = [doc.metadata["page"] for doc in result]
        assert pages == [1, 2]

    def test_sets_drawing_id_from_text(self, parser):
        page = self._make_mock_page("도면번호 DWG-5678 참조")
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([page]))
        mock_pdf.close = MagicMock()

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            result = parser.parse_drawing("/data/drawing.pdf")

        assert result[0].metadata["drawing_id"] == "DWG-5678"

    def test_sets_has_image_true_when_images_present(self, parser):
        page = self._make_mock_page("도면 내용", images=["img1"])
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([page]))
        mock_pdf.close = MagicMock()

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            result = parser.parse_drawing("/data/drawing.pdf")

        assert result[0].metadata["has_image"] is True

    def test_sets_doc_type_drawing(self, parser):
        page = self._make_mock_page("도면 내용")
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([page]))
        mock_pdf.close = MagicMock()

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            result = parser.parse_drawing("/data/drawing.pdf")

        assert result[0].metadata["doc_type"] == "drawing"

    def test_closes_pdf_after_iteration(self, parser):
        mock_pdf = MagicMock()
        mock_pdf.__iter__ = MagicMock(return_value=iter([]))
        mock_pdf.close = MagicMock()

        with patch("pipeline.adapters.site_a.fitz.open", return_value=mock_pdf):
            parser.parse_drawing("/data/drawing.pdf")

        mock_pdf.close.assert_called_once()
