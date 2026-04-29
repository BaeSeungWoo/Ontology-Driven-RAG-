# pipeline/parsers/upstage_parser.py
#
# 스캔본 PDF 파싱 전략
# Upstage Document AI: OCR + 레이아웃 분석 API 사용

import os
from pathlib import Path
from typing import Any

import upstage.divise_pdf as div_pdf
import upstage.upstage_scan as scan
import upstage.merge_scan_json as mge_json

from upstage.generate_chunks import process_document, save_jsonl
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

    def _extract(self, pdf_path: str, output_dir: Path) -> dict[str, Any]:
        """특정 폴더에 존재하는 PDF 목록들을 Upstage를 통하여 JSON 형태의 파일로 내보낸다.

        각 프로세스에 따른 결과 파일들이 저장되며 저장 형태는 Returns의 예시 형태로 저장된다.
        
        출력 JSON은 xxxx.json 형태로 출력.

        Args:
            pdf_path (str): 추출할 PDF 폴더 경로
            output_dir (str): upstage 추출물 결과들이 저장될 폴더 경로
        
        Returns:
            dict[str, Any] : 병합된 결과물
        Returns:
            예) input
                >>> 삼성화재.pdf

                output
                    split_pdfs (분할 된 PDF)
                    >>> output_dir/split_pdfs/삼성화재/part_1.pdf   
                    >>> output_dir/split_pdfs/삼성화재/part_2.pdf   

                    async_results (분할된 PDF 다운로드 경로가 적힌 JSON)
                    >>> output_dir/async_results/삼성화재/part_1.json   
                    >>> output_dir/async_results/삼성화재/part_2.json   

                    batch_jsons (다운로드 경로를 통해 추출 결과를 다운받은 JSON)
                    >>> output_dir/batch_jsons/삼성화재/part_1/0_part_1.pdf.json   
                    >>> output_dir/batch_jsons/삼성화재/part_1/1_part_1.pdf.json   
                    >>> output_dir/batch_jsons/삼성화재/part_2/0_part_2.pdf.json   

                    merged_jsons (최종 병합 결과 JSON)
                    >>> output_dir/merged_jsons/삼성화재.json   
        """
        input_pdf_path = Path(pdf_path)
        split_pdf_root_dir = output_dir / "split_pdfs"
        async_result_root_dir = output_dir / "async_results"
        batch_json_root_dir = output_dir / "batch_jsons"
        merged_output_dir = output_dir / "merged_jsons"

        divise_dir = div_pdf.split_all_pdfs_in_folder(
            pdf_path=input_pdf_path,
            output_root_dir=split_pdf_root_dir
        )

        scan.process_all_pdf(
            input_root_dir=divise_dir,
            async_result_root_dir=async_result_root_dir,
            batch_json_root_dir=batch_json_root_dir,
            api_key=self.api_key,
        )

        upstage_data = mge_json.merge_all_pdf_jsons(
            batch_json_root_dir=batch_json_root_dir / input_pdf_path.stem,
            merged_output_dir=merged_output_dir,
        )
        return upstage_data

    def parse(self, pdf_path: str, output_dir: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Docling 추출물을 실제 구조화 청크로 변환 후 폴더에 저장

        Args:
            pdf_path (str): docling 추출물 경로
            output_dir (dict[str, Any]): 각 구조화된 파일들이 저장될 경로

        Returns:
            list[dict[str, Any]]: 구조화된 청크
        """
        extract_dir = output_dir.get("extract")
        struct_dir = Path(output_dir.get("struct"))
        asset_dir = output_dir.get("asset")
        upstage_data = self._extract(pdf_path=pdf_path, output_dir=extract_dir)
        if not upstage_data:
            return None
        chunks = process_document(pdf_path=pdf_path, asset_root=asset_dir, data=upstage_data)
        output_path = Path(struct_dir) / f"{Path(pdf_path).stem}.jsonl"
        save_jsonl(chunks, output_path)
        return chunks