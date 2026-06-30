# pipeline/data_loader.py

from pathlib import Path
from typing import Any

from backend.app.factories.config import Config
from pipeline.adapters.base import BaseParser
from pipeline.ingestion.chunk_refiner import ChunkRefiner
from pipeline.ingestion.machine_resolver import (
    build_doc_to_machine_index,
    enrich_machine_codes,
)
from pipeline.ingestion.vector_writer import create_vector_collection, upsert

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
        "text": "parse_text"
    }

    def __init__(self, config: Config, adapter: BaseParser):
        self.config = config
        self.adapter = adapter
        self.chunk_refiner = ChunkRefiner(
            chunk_size=config.vector_db.chunk_size,
            chunk_overlap=config.vector_db.chunk_overlap,
        )
        self.doc_to_machine = build_doc_to_machine_index(config.machines)
        self.collection = create_vector_collection(config)

    def build_from(self, source_dir: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
        """해당 문서 타입에 따른 parse 전략을 실행하여 구조화 청크 반환 후 
        
        vectorDB에 들어갈 청크로 변환 및 vectorDB에 삽입.

        Args:
            source_dir (dict[str, Any]): 각 프로세스별 폴더 경로
            doc_type (str): 문서 타입
            reset (bool): vectorDB 재생성 여부
        """
        if doc_type not in self._PARSE_DISPATCH:
            raise ValueError(f"지원하지 않는 doc_type: '{doc_type}'. 허용값: {list(self._PARSE_DISPATCH)}")

        docs = self._load(source_dir, doc_type)
        chunks = self.chunk_refiner.convert(docs)
        print(f"[{self.config.id}][{doc_type}] {len(docs)}개 문서 → {len(chunks)}개 청크")

        enriched_chunks = enrich_machine_codes(chunks, self.doc_to_machine)

        upsert(
            collection=self.collection, 
            chunks=enriched_chunks, 
            id=self.config.id,
            db_path=self.config.vector_db.get_db_path("chroma")
        )
        return enriched_chunks

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
