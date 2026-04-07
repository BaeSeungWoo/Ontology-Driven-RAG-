# tests/unit/pipeline/test_upstage_parser.py

import os
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.documents import Document


class TestUpstageParserInit:
    def test_init_raises_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            # UPSTAGE_API_KEY 없이 생성 시 EnvironmentError
            env = {k: v for k, v in os.environ.items() if k != "UPSTAGE_API_KEY"}
            with patch.dict(os.environ, env, clear=True):
                from pipeline.parsers.upstage_parser import UpstageParser
                with pytest.raises(EnvironmentError):
                    UpstageParser()

    def test_init_uses_env_api_key(self):
        with patch.dict(os.environ, {"UPSTAGE_API_KEY": "env-key"}):
            from pipeline.parsers.upstage_parser import UpstageParser
            parser = UpstageParser()
            assert parser.api_key == "env-key"

    def test_init_uses_explicit_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            from pipeline.parsers.upstage_parser import UpstageParser
            parser = UpstageParser(api_key="explicit-key")
            assert parser.api_key == "explicit-key"


@pytest.fixture
def parser():
    with patch.dict(os.environ, {"UPSTAGE_API_KEY": "test-key"}):
        from pipeline.parsers.upstage_parser import UpstageParser
        return UpstageParser()


class TestUpstageParserParse:
    def test_posts_to_correct_url(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response) as mock_post:
            parser.parse(str(pdf_file))
            call_args = mock_post.call_args
            assert "api.upstage.ai" in call_args.args[0]

    def test_sends_auth_header(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response) as mock_post:
            parser.parse(str(pdf_file))
            headers = mock_post.call_args.kwargs["headers"]
            assert headers["Authorization"] == "Bearer test-key"

    def test_maps_elements_to_documents(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        # upstage_api_response에 3개 중 1개는 빈 content → 2개만 반환
        assert len(result) == 2
        assert all(isinstance(d, Document) for d in result)

    def test_skips_empty_content_elements(self, parser, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        response_with_empty = {
            "elements": [
                {"content": {"markdown": ""}, "type": "figure", "page": 1, "confidence": 0.8},
                {"content": {"markdown": "   "}, "type": "figure", "page": 1, "confidence": 0.8},
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = response_with_empty
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        assert result == []

    def test_sets_source_to_filename(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan_doc.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        for doc in result:
            assert doc.metadata["source"] == "scan_doc.pdf"

    def test_preserves_element_type_metadata(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        assert result[0].metadata["element_type"] == "heading"
        assert result[1].metadata["element_type"] == "paragraph"

    def test_preserves_page_number(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        assert result[0].metadata["page"] == 1

    def test_preserves_confidence(self, parser, upstage_api_response, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = upstage_api_response
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        assert result[0].metadata["confidence"] == 0.99

    def test_raises_on_http_error(self, parser, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("HTTP 401")

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            with pytest.raises(Exception):
                parser.parse(str(pdf_file))

    def test_empty_elements_list_returns_empty(self, parser, tmp_path):
        pdf_file = tmp_path / "scan.pdf"
        pdf_file.write_bytes(b"%PDF fake content")

        mock_response = MagicMock()
        mock_response.json.return_value = {"elements": []}
        mock_response.raise_for_status.return_value = None

        with patch("pipeline.parsers.upstage_parser.requests.post", return_value=mock_response):
            result = parser.parse(str(pdf_file))

        assert result == []
