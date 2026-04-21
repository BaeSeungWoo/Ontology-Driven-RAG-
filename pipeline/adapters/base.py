# pipeline/adapters/base.py

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

class BaseParser(ABC):
    """
    사이트별 파서 인터페이스.

    매뉴얼 파싱은 두 경로로 나뉩니다.
      parse_manual  → 일반 PDF 매뉴얼  (Docling 사용)
      parse_scanned → 스캔본 PDF       (Upstage Document AI 사용)
      parse_drawing → 설비 도면
    """

    @abstractmethod
    def parse_manual(self, file_path: str) -> list[dict[str, Any]]:
        """일반 텍스트 기반 PDF 매뉴얼을 파싱합니다 (Docling)."""

    @abstractmethod
    def parse_scanned(self, file_path: str) -> list[dict[str, Any]]:
        """스캔 이미지 기반 PDF를 파싱합니다 (Upstage OCR)."""

    @abstractmethod
    def parse_drawing(self, file_path: str) -> list[dict[str, Any]]:
        """도면 파일을 파싱합니다."""

    @staticmethod
    def _make_doc(content: str, source: str, doc_type: str, **extra) -> dict[str, Any]:
        return {
            "page_content": content,
            "metadata": {"source": Path(source).name, "doc_type": doc_type, **extra},
        }