# pipeline/parsers/docling_parser.py
#
# 일반 텍스트 기반 PDF 매뉴얼 파싱 전략
# Docling: 레이아웃 인식 + 표·제목 구조 보존

from pathlib import Path
from typing import List

from docling.document_converter import DocumentConverter
from langchain_core.documents import Document


class DoclingParser:
    """
    Docling 기반 일반 매뉴얼 파서.
    표·제목·단락 구조를 보존하면서 Markdown 형태로 변환합니다.

    설치: pip install docling
    """

    def __init__(self):
        self.converter = DocumentConverter()

    def parse(self, file_path: str) -> List[Document]:
        """
        PDF를 Markdown 구조로 변환한 뒤 섹션(## 헤딩) 단위로 분할합니다.
        섹션이 없는 경우 전체 텍스트를 단일 Document로 반환합니다.
        """
        result = self.converter.convert(file_path)
        full_md = result.document.export_to_markdown()

        sections = self._split_by_heading(full_md)
        source_name = Path(file_path).name

        return [
            Document(
                page_content=section.strip(),
                metadata={
                    "source": source_name,
                    "doc_type": "manual",
                    "parser": "docling",
                    "section_index": idx,
                },
            )
            for idx, section in enumerate(sections)
            if section.strip()
        ]

    @staticmethod
    def _split_by_heading(markdown: str) -> List[str]:
        """## 헤딩 기준으로 섹션을 분리합니다."""
        import re
        parts = re.split(r"(?=^## )", markdown, flags=re.MULTILINE)
        return parts if len(parts) > 1 else [markdown]