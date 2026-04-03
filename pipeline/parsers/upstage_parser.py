# pipeline/parsers/upstage_parser.py
#
# 스캔본 PDF 파싱 전략
# Upstage Document AI: OCR + 레이아웃 분석 API 사용

import os
from pathlib import Path
from typing import List

import requests
import fitz  # PyMuPDF
from langchain_core.documents import Document


class UpstageParser:
    """
    Upstage Document Parse API 기반 스캔본 파서.
    이미지·손글씨·인쇄물 혼합 PDF에 사용합니다.

    설치: pip install requests
    환경변수: UPSTAGE_API_KEY
    API 문서: https://developers.upstage.ai/docs/apis/doc-parse
    """

    API_URL = "https://api.upstage.ai/v1/document-ai/document-parse"

    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("UPSTAGE_API_KEY")
        if not self.api_key:
            raise EnvironmentError(
                "UPSTAGE_API_KEY 환경변수가 설정되지 않았습니다."
            )

    def parse(self, file_path: str) -> List[Document]:
        """
        Upstage API로 스캔본을 파싱합니다.
        API 응답의 elements 배열을 element 단위 Document로 변환합니다.
        """
        with open(file_path, "rb") as f:
            response = requests.post(
                self.API_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"document": f},
                data={"output_formats": '["markdown"]'},
            )
        response.raise_for_status()
        data = response.json()

        source_name = Path(file_path).name
        docs = []

        for element in data.get("elements", []):
            content = element.get("content", {}).get("markdown", "").strip()
            if not content:
                continue
            docs.append(Document(
                page_content=content,
                metadata={
                    "source": source_name,
                    "doc_type": "scanned_manual",
                    "parser": "upstage",
                    "element_type": element.get("type", ""),
                    "page": element.get("page", 0),
                    "confidence": element.get("confidence", 1.0),
                },
            ))

        return docs