# pipeline/adapters/site_b.py
#
# B 사이트 특화 파서
#   - 도면:   PDF 도면 (PyMuPDF)
#   - 사양서: Excel (.xlsx) → 일반 매뉴얼로 처리 (Docling은 PDF 전용이므로 openpyxl 사용)
#   - 스캔본: 스캔 PDF (Upstage)

from typing import List, Any
from pathlib import Path

import json
import fitz  # PyMuPDF
import openpyxl

from pipeline.adapters.base import BaseParser
from pipeline.parsers.docling_parser import DoclingParser
from pipeline.parsers.upstage_parser import UpstageParser


class SiteBParser(BaseParser):

    def __init__(self):
        self._docling = DoclingParser()
        self._upstage = UpstageParser()

    # ── 일반 매뉴얼 (Docling / Excel 자동 분기) ────────────────────────

    def parse_manual(self, file_path: str, source_dir: dict[str, Any]) -> list[dict[str, Any]]:
        """
        확장자에 따라 파싱 전략을 자동 선택합니다.
          .pdf  → Docling (텍스트 구조 보존)
          .xlsx → openpyxl (행 단위 Document 변환)
        """
        if file_path.endswith(".xlsx"):
            return self._parse_excel(file_path)
        docs = self._docling.parse(pdf_path=file_path,output_dir=source_dir)
        for doc in docs:
            doc["metadata"]["site"] = "B"
        return docs

    # ── 스캔본 (Upstage) ──────────────────────────────────────────────

    def parse_scanned(self, file_path: str) -> list[dict[str, Any]]:
        """스캔 이미지 PDF — Upstage OCR로 텍스트 추출."""
        with Path(file_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
            docs = self._upstage.parse(data)
        for doc in docs:
            doc["metadata"]["site"] = "B"
        return docs

    # ── 도면 (PyMuPDF) ────────────────────────────────────────────────

    def parse_drawing(self, file_path: str) -> list[dict[str, Any]]:
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
                site="B",
                page=page_num,
            ))
        pdf.close()
        return docs

    # ── 내부: Excel 파싱 ──────────────────────────────────────────────

    def _parse_excel(self, file_path: str) -> list[dict[str, Any]]:
        """Excel 사양서 — 시트별, 행 단위로 Document를 생성합니다."""
        docs = []
        wb = openpyxl.load_workbook(file_path, data_only=True)

        for sheet in wb.worksheets:
            headers = [cell.value for cell in sheet[1] if cell.value]
            if not headers:
                continue

            for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
                row_text = "\n".join(
                    f"{headers[i]}: {val}"
                    for i, val in enumerate(row)
                    if i < len(headers) and val is not None
                )
                if not row_text.strip():
                    continue
                docs.append(self._make_doc(
                    content=row_text,
                    source=file_path,
                    doc_type="spec",
                    site="B",
                    sheet=sheet.title,
                    row=row_idx,
                ))

        wb.close()
        return docs