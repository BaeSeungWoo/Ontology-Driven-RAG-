# pipeline/data_loader.py

from pathlib import Path
from typing import Any
import pypdfium2 as pdfium

from backend.app.factories.config import Config
from pipeline.adapters.base import BaseParser
from pipeline.ingestion.chunk_refiner import ChunkRefiner
from pipeline.parsers.mnemonic_ladder import build_mnemonic_files
from pipeline.ingestion.machine_resolver import (
    build_doc_to_machine_index,
    enrich_machine_codes,
    _resolve_machine_code
)

class DataLoader:
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

    def load_text_from(self, source_dir: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
        """해당 문서 타입에 따른 parse 전략을 실행하여 구조화 청크 반환 후 
        
        vectorDB에 들어갈 청크로 변환 및 vectorDB에 삽입.

        Args:
            source_dir (dict[str, Any]): 각 프로세스별 폴더 경로
            doc_type (str): 문서 타입
            reset (bool): vectorDB 재생성 여부
        """
        if doc_type not in self._PARSE_DISPATCH:
            raise ValueError(f"지원하지 않는 doc_type: '{doc_type}'. 허용값: {list(self._PARSE_DISPATCH)}")

        docs = self._load_text(source_dir, doc_type)
        chunks = self.chunk_refiner.convert(docs)
        print(f"[{self.config.id}][{doc_type}] {len(docs)}개 문서 → {len(chunks)}개 청크")

        enriched_chunks = enrich_machine_codes(chunks, self.doc_to_machine)
        return enriched_chunks

    def _load_text(self, source_dir: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
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

    def load_image_from(
        self,
        source_dir: dict[str, Any],
        doc_type: str,
        output_dir: str | Path,
        render_dpi: int = 100,
    ) -> list[dict[str, Any]]:
        input_dir = Path(source_dir.get("input", ""))
        out_dir = Path(output_dir) / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)

        rows = []
        scale = render_dpi / 72.0

        if not input_dir.exists():
            return rows

        for pdf_path in sorted(input_dir.rglob("*.pdf")):
            doc_name = pdf_path.stem
            doc_out_dir = out_dir / doc_name
            doc_out_dir.mkdir(parents=True, exist_ok=True)

            doc = pdfium.PdfDocument(str(pdf_path))
            doc_pages = len(doc)
            try:
                for page_idx in range(doc_pages):
                    page = doc[page_idx]
                    try:
                        pil = page.render(scale=scale).to_pil()
                        image_path = doc_out_dir / f"page_{page_idx + 1:04d}.png"
                        pil.save(image_path)

                        machine_codes = _resolve_machine_code(doc_name, self.doc_to_machine)

                        rows.append({
                            "doc_type": doc_type,
                            "source_doc_name": doc_name,
                            "page_num": page_idx + 1,
                            "image_path": str(image_path),
                            "source_path": str(pdf_path),
                            "machine_code": machine_codes,
                        })
                    finally:
                        page.close()
            finally:
                doc.close()
            print(f"rendered {doc_pages} pages of {doc_name}")
        return rows

    def load_ladder_from(self, source_dir: dict[str, Any], doc_type: str) -> list[dict[str, Any]]:
        """LST 미모닉 구조화 이후 VectorDB 저장용 청크로 변환"""

        input_dir = Path(source_dir["input"])
        struct_dir = Path(source_dir["struct"])
        lst_files = sorted(input_dir.glob("*.LST"))
    
        # .LST 파일이 1개인지 확인
        if len(lst_files) != 1:
            raise ValueError(
                f"Expected exactly one .LST file in {input_dir}, "
                f"but found {len(lst_files)}"
            )
    
        source_file = lst_files[0]
        ladder_dict = build_mnemonic_files(
            input_file=source_file,
            output_dir=struct_dir,
        )

        docs = self.chunk_refiner.ladder_convert(
            raw_chunks=ladder_dict,
            site_id=self.config.id,
        )

        docs = enrich_machine_codes(docs, self.doc_to_machine)

        print(f"[{self.config.id}][{doc_type}] {len(docs)}개 래더 청크 생성")
        return docs