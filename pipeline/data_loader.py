# pipeline/data_loader.py

import hashlib
from pathlib import Path
from typing import List

from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.factories.config import Config
from app.embeddings import load_embeddings, save_embedding_meta
from pipeline.adapters.base import BaseParser


class DocumentParser:
    def __init__(self, chunk_size: int = 800, chunk_overlap: int = 150):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ".", " ", ""],
        )

    def split(self, docs: List[Document]) -> List[Document]:
        chunks = self.splitter.split_documents(docs)
        for chunk in chunks:
            chunk.metadata["chunk_id"] = hashlib.md5(chunk.page_content.encode()).hexdigest()[:12]
        return chunks


class VectorDBBuilder:
    """
    어댑터를 주입받아 doc_type 별 파싱 전략을 실행합니다.

    doc_type 허용값:
        "manual"   → adapter.parse_manual()   일반 PDF (Docling)
        "scanned"  → adapter.parse_scanned()  스캔본 PDF (Upstage)
        "drawing"  → adapter.parse_drawing()  도면
    """

    _PARSE_DISPATCH = {
        "manual":  "parse_manual",
        "scanned": "parse_scanned",
        "drawing": "parse_drawing",
    }

    def __init__(self, config: Config, adapter: BaseParser):
        self.config = config
        self.adapter = adapter
        self.embeddings = load_embeddings(config)
        self.parser = DocumentParser(
            chunk_size=config.vector_db.chunk_size,
            chunk_overlap=config.vector_db.chunk_overlap,
        )

    def build_from(self, source_dir: str, doc_type: str, reset: bool = False) -> Chroma:
        if doc_type not in self._PARSE_DISPATCH:
            raise ValueError(f"지원하지 않는 doc_type: '{doc_type}'. 허용값: {list(self._PARSE_DISPATCH)}")

        if reset and Path(self.config.vector_db.db_path).exists():
            import shutil
            shutil.rmtree(self.config.vector_db.db_path)
            print(f"[{self.config.id}] 기존 DB 삭제")

        docs = self._load(source_dir, doc_type)
        chunks = self.parser.split(docs)
        print(f"[{self.config.id}][{doc_type}] {len(docs)}개 문서 → {len(chunks)}개 청크")

        db = self._upsert(chunks)
        save_embedding_meta(self.config)
        return db

    def _load(self, source_dir: str, doc_type: str) -> List[Document]:
        parse_fn = getattr(self.adapter, self._PARSE_DISPATCH[doc_type])
        docs = []
        for file_path in sorted(Path(source_dir).rglob("*")):
            if not file_path.is_file():
                continue
            parsed = parse_fn(str(file_path))
            for doc in parsed:
                doc.metadata["site_id"] = self.config.id
            docs.extend(parsed)
        return docs

    def _upsert(self, chunks: List[Document]) -> Chroma:
        ids = [c.metadata["chunk_id"] for c in chunks]
        db = Chroma(persist_directory=self.config.vector_db.db_path, embedding_function=self.embeddings)
        db.add_documents(documents=chunks, ids=ids)
        print(f"[{self.config.id}] 저장 완료 → {self.config.vector_db.db_path}")
        return db