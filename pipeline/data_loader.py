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
        "excel": "parse_excel"
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
        self.machine_list = self.config.machines

        # 빠른 조회 용
        self._doc_to_machine = {}
        for machine_code, info in self.machine_list.items():
            for doc_name in info.get("document", []):
                key = doc_name
                self._doc_to_machine.setdefault(key, []).append(machine_code)
        # self.collection = self.vectordb_client.get_or_create_collection(
        #     name=self.config.id,
        #     # name="test_a",
        #     embedding_function=self.embedding,
        #     metadata={"hnsw:space": "cosine"}
        # )
    
    def _get_collection_name(self, machine_code: str) -> str:
        return f"{self.config.id}_{machine_code}"

    def _get_collection(self, machine_code: str):
        return self.vectordb_client.get_or_create_collection(
            name=self._get_collection_name(machine_code),
            embedding_function=self.embedding,
            metadata={"hnsw:space": "cosine"}
        )

    def _resolve_machine_code(self, source_doc_name: str) -> str | None:
        """metadata.source_doc_name → machine_code 매핑.
        
        파일명(확장자 포함)으로 우선 조회하고,
        못 찾으면 stem(확장자 제외)으로 부분 매칭을 시도합니다.
        """
        key = source_doc_name
        if key in self._doc_to_machine:
            return self._doc_to_machine[key]

        # 부분 매칭 fallback: JSON 문서명이 source_doc_name을 포함하거나 그 반대
        for doc_name, machine_code in self._doc_to_machine.items():
            if key in doc_name or doc_name in key:
                return machine_code

        return None  # 매칭 실패

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

        self._upsert_by_machine(chunks)
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

    def _upsert_by_machine(self, chunks: list[dict[str, Any]]):
        """청크를 machine_code별로 그룹핑한 뒤 각 collection에 upsert."""
        if not chunks:
            print("저장할 청크 데이터가 없습니다")
            return

        # 1) machine_code별 그룹핑
        groups: dict[str, list[dict[str, Any]]] = {}
        unmatched: list[dict[str, Any]] = []

        for chunk in chunks:
            source_doc_name = chunk["metadata"].get("source_doc_name", "")
            machine_code = self._resolve_machine_code(source_doc_name)

            if machine_code is None:
                unmatched.append(chunk)
                continue

            codes = machine_code if isinstance(machine_code, list) else [machine_code]
            for code in codes:
                groups.setdefault(code, []).append(chunk)

        if unmatched:
            print(
                f"[경고] machine_code 매칭 실패 청크 {len(unmatched)}개 — "
                "source_doc_name을 JSON document 목록과 비교해 확인하세요."
            )

        # 2) 그룹별 upsert
        for machine_code, group_chunks in groups.items():
            collection = self._get_collection(machine_code)
            print(
                f"  [{machine_code}] collection: {self._get_collection_name(machine_code)}, "
                f"청크 수: {len(group_chunks)}"
            )
            self._upsert(collection, group_chunks)

        print(f"[{self.config.id}] 저장 완료 → {self.config.vector_db.db_path}")

    def _upsert(self, collection, chunks: list[dict[str, Any]]):
        """청크를 받아 vectorDB에 삽입
        
        Args:
            chunks (list[dict[str, Any]]): vectorDB 형식에 맞게 변환된 청크
        """
        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i: i+batch_size]

            # 핵심 수정: documents 리스트를 만들 때 "passage: " 접두사를 추가합니다.
            processed_documents = [f"passage: {doc['page_content']}" for doc in batch]

            collection.add(
                ids=[doc["id"] for doc in batch],
                documents=processed_documents,  # 접두사가 붙은 텍스트 전달
                metadatas=[doc["metadata"] for doc in batch]
            )
            print(f"  - 진행률: {min(i + batch_size, len(chunks))}/{len(chunks)}")
        # ids = [c.metadata["chunk_id"] for c in chunks]
        # db.add_documents(documents=chunks, ids=ids)
        print(f"[{self.config.id}] 저장 완료 → {self.config.vector_db.db_path}")
