# pipeline/adapters/site_a.py
#
# A 사이트 특화 파서
#   - 도면:   PDF 기반 설비 도면 (PyMuPDF)
#   - 매뉴얼: 일반 PDF (Docling)
#   - 스캔본: 스캔 PDF (Upstage)

import re
from typing import List, Any
from pathlib import Path
import json

import fitz  # PyMuPDF

from pipeline.adapters.base import BaseParser
from pipeline.parsers.docling_parser import DoclingParser
from pipeline.parsers.upstage_parser import UpstageParser
from pipeline.parsers.text_parser import TextParser

class SiteAParser(BaseParser):

    def __init__(self):
        self._docling = DoclingParser()
        self._upstage = UpstageParser()
        self._text = TextParser()
        
    # ── 일반 매뉴얼 (Docling) ──────────────────────────────────────────

    def parse_manual(self, file_path: str, source_dir: dict[str, Any]) -> list[dict[str, Any]]:
        """일반 텍스트 PDF 매뉴얼 — Docling으로 섹션 구조 보존."""
        docs = self._docling.parse(pdf_path=file_path,output_dir=source_dir)
        for doc in docs:
            doc["metadata"]["site"] = "yunam"
        return docs

    # ── 스캔본 (Upstage) ──────────────────────────────────────────────

    def parse_scanned(self, file_path: str, source_dir: dict[str, Any]) -> list[dict[str, Any]]:
        """스캔 이미지 PDF — Upstage OCR로 텍스트 추출."""
        docs = self._upstage.parse(pdf_path=file_path,output_dir=source_dir)
        for doc in docs:
            doc["metadata"]["site"] = "yunam"
        return docs
    
    def parse_text(self, file_path: str, source_dir: dict[str, Any]) -> list[dict[str, Any]]:
        docs = self._text.parse(txt_path=file_path,output_dir=source_dir)
        for doc in docs:
            doc["metadata"]["site"] = "yunam"
        return docs

    # ── 도면 (PyMuPDF) ────────────────────────────────────────────────

    def parse_drawing(self, file_path: str) -> list[dict[str, Any]]:
        """설비 도면 PDF — 도면 번호(DWG-XXXX)를 메타데이터로 추출."""
        docs = []
        pdf = fitz.open(file_path)

        for page_num, page in enumerate(pdf, start=1):
            text = page.get_text("text").strip()
            if not text:
                continue

            docs.append(self._make_doc(
                content=text,
                source=file_path,
                doc_type="drawing",
                site="yunam",
                page=page_num,
                drawing_id=self._extract_drawing_id(text),
                has_image=len(page.get_images()) > 0,
            ))

        pdf.close()
        return docs

    @staticmethod
    def _extract_drawing_id(text: str) -> str:
        match = re.search(r"DWG-\d+", text)
        return match.group(0) if match else ""