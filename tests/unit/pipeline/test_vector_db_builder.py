# tests/unit/pipeline/test_vector_db_builder.py

import os
import pytest
from unittest.mock import patch, MagicMock, call
from langchain_core.documents import Document


@pytest.fixture
def builder(ollama_config):
    with patch("pipeline.data_loader.load_embeddings") as mock_load, \
         patch("pipeline.data_loader.Chroma") as MockChroma:
        mock_load.return_value = MagicMock()
        MockChroma.return_value = MagicMock()
        from pipeline.data_loader import VectorDBBuilder
        adapter = MagicMock()
        b = VectorDBBuilder(ollama_config, adapter)
        b._mock_adapter = adapter
        b._MockChroma = MockChroma
        yield b


class TestBuildFromDispatch:
    def test_invalid_doc_type_raises_valueerror(self, builder, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            builder.build_from(str(tmp_path), "invalid_type")
        assert "invalid_type" in str(exc_info.value)

    def test_valueerror_message_lists_allowed_types(self, builder, tmp_path):
        with pytest.raises(ValueError) as exc_info:
            builder.build_from(str(tmp_path), "unknown")
        error_msg = str(exc_info.value)
        assert "manual" in error_msg
        assert "scanned" in error_msg
        assert "drawing" in error_msg

    def test_manual_calls_parse_manual(self, builder, tmp_path):
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"dummy")
        builder._mock_adapter.parse_manual.return_value = [
            Document(page_content="내용", metadata={"source": "doc.pdf"})
        ]
        builder.build_from(str(tmp_path), "manual")
        builder._mock_adapter.parse_manual.assert_called()

    def test_scanned_calls_parse_scanned(self, builder, tmp_path):
        test_file = tmp_path / "scan.pdf"
        test_file.write_bytes(b"dummy")
        builder._mock_adapter.parse_scanned.return_value = [
            Document(page_content="내용", metadata={"source": "scan.pdf"})
        ]
        builder.build_from(str(tmp_path), "scanned")
        builder._mock_adapter.parse_scanned.assert_called()

    def test_drawing_calls_parse_drawing(self, builder, tmp_path):
        test_file = tmp_path / "draw.pdf"
        test_file.write_bytes(b"dummy")
        builder._mock_adapter.parse_drawing.return_value = [
            Document(page_content="도면 내용", metadata={"source": "draw.pdf"})
        ]
        builder.build_from(str(tmp_path), "drawing")
        builder._mock_adapter.parse_drawing.assert_called()


class TestBuildFromReset:
    def test_reset_true_removes_existing_db(self, builder, tmp_path, ollama_config):
        # db_path 디렉토리를 실제로 만들어야 shutil.rmtree가 호출됨
        import os
        db_dir = tmp_path / "chroma"
        db_dir.mkdir()
        ollama_config.vector_db.db_path = str(db_dir)

        builder._mock_adapter.parse_manual.return_value = []

        with patch("shutil.rmtree") as mock_rmtree:
            builder.build_from(str(tmp_path), "manual", reset=True)
            mock_rmtree.assert_called_once_with(str(db_dir))

    def test_reset_false_keeps_existing_db(self, builder, tmp_path):
        builder._mock_adapter.parse_manual.return_value = []
        with patch("shutil.rmtree") as mock_rmtree:
            builder.build_from(str(tmp_path), "manual", reset=False)
            mock_rmtree.assert_not_called()


class TestLoad:
    def test_adds_site_id_to_all_docs(self, builder, tmp_path, ollama_config):
        test_file = tmp_path / "doc.pdf"
        test_file.write_bytes(b"dummy")
        builder._mock_adapter.parse_manual.return_value = [
            Document(page_content="내용", metadata={"source": "doc.pdf"})
        ]
        docs = builder._load(str(tmp_path), "manual")
        for doc in docs:
            assert doc.metadata["site_id"] == ollama_config.id

    def test_iterates_all_files_in_dir(self, builder, tmp_path):
        for i in range(3):
            (tmp_path / f"file{i}.pdf").write_bytes(b"dummy")
        builder._mock_adapter.parse_manual.return_value = [
            Document(page_content="내용", metadata={})
        ]
        builder._load(str(tmp_path), "manual")
        assert builder._mock_adapter.parse_manual.call_count == 3


class TestUpsert:
    def test_uses_chunk_id_as_chroma_id(self, builder):
        chunks = [
            Document(page_content="청크1", metadata={"chunk_id": "abc123def456"}),
            Document(page_content="청크2", metadata={"chunk_id": "fed654cba321"}),
        ]
        mock_db = MagicMock()
        builder._MockChroma.return_value = mock_db
        builder._upsert(chunks)
        call_kwargs = mock_db.add_documents.call_args.kwargs
        assert call_kwargs["ids"] == ["abc123def456", "fed654cba321"]
