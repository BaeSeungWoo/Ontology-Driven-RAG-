"""Render original PDF pages for multimodal indexing; no OCR or text parsing."""
from pathlib import Path
from typing import Any
import pypdfium2 as pdfium

from backend.app.factories.config import Config
from pipeline.ingestion.machine_resolver import build_doc_to_machine_index, _resolve_machine_code


class DataLoader:
    """PDF page rendering used by the separate multimodal build stage."""

    def __init__(self, config: Config):
        self.config = config
        self.doc_to_machine = build_doc_to_machine_index(config.machines)

    def load_image_from(
        self,
        source_dir: dict[str, Any],
        doc_type: str,
        output_dir: str | Path,
        render_dpi: int = 100,
        allowed_document_names: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        input_dir = Path(source_dir.get("input", ""))
        out_dir = Path(output_dir) / "pages"
        out_dir.mkdir(parents=True, exist_ok=True)

        rows = []
        scale = render_dpi / 72.0

        if not input_dir.exists():
            return rows

        for pdf_path in sorted(input_dir.rglob("*.pdf")):
            if allowed_document_names is not None:
                from pipeline.ingestion.prepared_documents import document_key
                if document_key(pdf_path.name) not in allowed_document_names:
                    continue
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
