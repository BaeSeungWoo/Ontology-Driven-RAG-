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
import upstage.divise_pdf as div_pdf
import upstage.upstage_scan as scan
import upstage.merge_scan_json as mge_json


class UpstageParser:
    """
    Upstage Document Parse API 기반 스캔본 파서.
    이미지·손글씨·인쇄물 혼합 PDF에 사용합니다.

    설치: pip install requests PyMuPDF
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

    def extract(self, input_dir: Path, output_dir: Path) -> None:
        """특정 폴더에 존재하는 PDF 목록들을 Upstage를 통하여 JSON 형태의 파일로 내보낸다.

        각 프로세스에 따른 결과 파일들이 저장되며 저장 형태는 Returns의 예시 형태로 저장된다.
        
        출력 JSON은 xxxx.json 형태로 출력된다.

        Args:
            input_dir (str): 추출할 PDF 폴더 경로
            output_dir (str): upstage 추출물 결과들이 저장될 폴더 경로
        
        Returns:
            예) input
                >>> input_dir/삼성화재.pdf
                >>> input_dir/현대해상.pdf

                output
                    split_pdfs (분할 된 PDF)
                    >>> output_dir/split_pdfs/삼성화재/part_1.pdf   
                    >>> output_dir/split_pdfs/삼성화재/part_2.pdf   
                    >>> output_dir/split_pdfs/현대해상/part_1.pdf   

                    async_results (분할된 PDF 다운로드 경로가 적힌 JSON)
                    >>> output_dir/async_results/삼성화재/part_1.json   
                    >>> output_dir/async_results/삼성화재/part_2.json   
                    >>> output_dir/async_results/현대해상/part_1.json   

                    batch_jsons (다운로드 경로를 통해 추출 결과를 다운받은 JSON)
                    >>> output_dir/batch_jsons/삼성화재/part_1/0_part_1.pdf.json   
                    >>> output_dir/batch_jsons/삼성화재/part_1/1_part_1.pdf.json   
                    >>> output_dir/batch_jsons/삼성화재/part_2/0_part_2.pdf.json   
                    >>> output_dir/batch_jsons/현대해상/part_1/0_part_1.pdf.json   

                    merged_jsons (최종 병합 결과 JSON)
                    >>> output_dir/merged_jsons/삼성화재.json   
                    >>> output_dir/merged_jsons/현대해상.json   
        """
        split_pdf_root_dir = output_dir / "split_pdfs"
        async_result_root_dir = output_dir / "async_results"
        batch_json_root_dir = output_dir / "batch_jsons"
        merged_output_dir = output_dir / "merged_jsons"

        div_pdf.split_all_pdfs_in_folder(
            input_dir=input_dir,
            output_root_dir=split_pdf_root_dir
        )

        scan.process_all_pdf(
            input_root_dir=split_pdf_root_dir,
            async_result_root_dir=async_result_root_dir,
            batch_json_root_dir=batch_json_root_dir,
            api_key=self.api_key,
        )

        mge_json.merge_all_pdf_jsons(
            batch_json_root_dir=batch_json_root_dir,
            split_pdf_root_dir=split_pdf_root_dir,
            merged_output_dir=merged_output_dir,
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