# pipeline/data_loader.py

import hashlib
from pathlib import Path
from typing import List, Any

import chromadb

from backend.app.factories.config import Config
from backend.app.embeddings import load_embeddings, save_embedding_meta
from pipeline.adapters.base import BaseParser
from chunk_builder import ChunkBuilder

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
        self.parser = ChunkBuilder(
            chunk_size=config.vector_db.chunk_size,
            chunk_overlap=config.vector_db.chunk_overlap,
        )
        self.vectordb_client = chromadb.PersistentClient(path=self.config.vector_db.db_path)
        self.embedding = load_embeddings(self.config)
        self.collection = self.vectordb_client.get_or_create_collection(
            # name=self.config.id,
            name="test_a",
            embedding_function=self.embedding,
            metadata={"hnsw:space": "cosine"}
        )

    def build_from(self, source_dir: dict[str, Any], doc_type: str, reset: bool = False):
        """해당 문서 타입에 따른 parse 전략을 실행하여 구조화 청크 반환 후 
        
        vectorDB에 들어갈 청크로 변환 및 vectorDB에 삽입.

        Args:
            source_dir (dict[str, Any]): 각 프로세스별 폴더 경로
            doc_type (str): 문서 타입
            reset (bool): vectorDB 재생성 여부
        """
        if doc_type not in self._PARSE_DISPATCH:
            raise ValueError(f"지원하지 않는 doc_type: '{doc_type}'. 허용값: {list(self._PARSE_DISPATCH)}")

        if reset and Path(self.config.vector_db.db_path).exists():
            import shutil
            shutil.rmtree(self.config.vector_db.db_path)
            print(f"[{self.config.id}] 기존 DB 삭제")

        docs = self._load(source_dir, doc_type)
        chunks = self.parser.convert(docs)
        print(f"[{self.config.id}][{doc_type}] {len(docs)}개 문서 → {len(chunks)}개 청크")

        self._upsert(chunks)
        save_embedding_meta(self.config)

    def _load(self, source_dir: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
        """해당 문서 타입에 따른 parse 전략을 실행하여 구조화 청크 반환 

        Args:
            source_dir (dict[str, Any]): 각 프로세스별 폴더 경로
            doc_type (str): 문서 타입
        """
        parse_fn = getattr(self.adapter, self._PARSE_DISPATCH[doc_type])
        docs = []
        input_dir = source_dir.get("input", "")
        if not input_dir:
            raise FileNotFoundError("PDF 폴더를 찾을 수 없습니다.")
        for file_path in sorted(Path(input_dir).rglob("*")):
            if not file_path.is_file():
                continue
            parsed = parse_fn(str(file_path), source_dir)
            if not parsed:
                continue
            for doc in parsed:
                doc["metadata"]["site_id"] = self.config.id
            docs.extend(parsed)
        return docs

    def _upsert(self, chunks: list[dict[str, Any]]):
        """청크를 받아 vectorDB에 삽입
        
        Args:
            chunks (list[dict[str, Any]]): vectorDB 형식에 맞게 변환된 청크
        """
        if not chunks:
            print("저장할 청크 데이터가 없습니다")
            return

        print(f"총 {len(chunks)}개 청크를 저장합니다.")
        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i+batch_size]

            # 핵심 수정: documents 리스트를 만들 때 "passage: " 접두사를 추가합니다.
            processed_documents = [f"passage: {doc['page_content']}" for doc in batch]

            self.collection.add(
                ids=[doc["id"] for doc in batch],
                documents=processed_documents,  # 접두사가 붙은 텍스트 전달
                metadatas=[doc["metadata"] for doc in batch]
            )
            print(f"  - 진행률: {min(i + batch_size, len(chunks))}/{len(chunks)}")
        # ids = [c.metadata["chunk_id"] for c in chunks]
        # db.add_documents(documents=chunks, ids=ids)
        print(f"[{self.config.id}] 저장 완료 → {self.config.vector_db.db_path}")
