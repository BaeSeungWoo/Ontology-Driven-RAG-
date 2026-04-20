# pipeline/parsers/docling_parser.py
#
# 일반 텍스트 기반 PDF 매뉴얼 파싱 전략
# Docling: 레이아웃 인식 + 표·제목 구조 보존

import time
from pathlib import Path
from typing import Any
import json
import re
import shutil
import tempfile
import torch
from doclings.generate_chunks import process_document, save_jsonl

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions

class DoclingParser:
    """
    Docling 기반 일반 매뉴얼 파서.
    표·제목·단락 구조를 보존하면서 Markdown 형태로 변환합니다.

    설치: pip install docling torch
    """

    def __init__(self):
        pass

    def _create_converter(self) -> DocumentConverter:
        """호출될 때마다 새로운 DocumentConverter 객체를 생성합니다."""
        if torch.cuda.is_available():
            pipeline_options = PdfPipelineOptions(
                accelerator_options=AcceleratorOptions(
                    device="cuda:1",
                    num_threads=4 # 커밋 수치를 줄이기 위해 4 -> 2 하향 추천
                ),
                ocr_batch_size = 4,    # 8 -> 4 하향
                layout_batch_size = 16, # 32 -> 4 (커밋 폭주 방지 핵심)
                do_ocr = False,
            )
            pdf_option = PdfFormatOption(pipeline_options=pipeline_options)
        else:
            pdf_option = PdfFormatOption(
                pipeline_options=PdfPipelineOptions(do_ocr=False)
            )

        return DocumentConverter(
            format_options={InputFormat.PDF: pdf_option}
        )

    def extract(self, pdf_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
        """해당 PDF 파일 경로를 읽어 Docling을 통하여 JSON 형태의 파일로 내보낸다.

        파일 명의 경우 반드시 영어, 숫자, _으로만 구성될 수 있으며,
        한글, 특수 문자 등 파일 시스템 상 안전하지 않은 문자가 들어가 있을 경우
        docling 라이브러리 내부에서 오류를 내보내므로 주의

        출력 JSON은 output_result_xxx.json 형태로 출력된다.

        Args:
            pdf_path (str): 추출할 PDF 경로
            output_dir (str): Docling 추출물 결과들이 저장될 폴더 경로
        
        Returns:
            예) docling_result.json 
        """
        pdf_to_docling = Path(pdf_path)
        extract_dir = Path(output_dir)

        converter = self._create_converter()
        try:
            start_time = time.time()
            
            # [핵심] 한글 문제를 피하기 위해 임시 영문 파일로 복사하여 진행
            with tempfile.TemporaryDirectory() as td:
                tmp_path = Path(td) / "input.pdf"   # 경로만 만들고
                shutil.copy2(pdf_to_docling, tmp_path)  # 복사 후
                conv_result = converter.convert(tmp_path)  # 변환
                pipeline_runtime = time.time() - start_time

                if conv_result.status != ConversionStatus.SUCCESS:
                    print(f"변환 실패: {pdf_to_docling.name}")
                    return None

                print(f"Document converted in {pipeline_runtime:.2f} seconds.")

                # 1. 결과를 딕셔너리 형태로 변환
                dist_data = conv_result.document.export_to_dict()
                
                # 결과 데이터에는 원본 한글 이름을 보존 (사용자 편의성)
                dist_data["original_name"] = pdf_to_docling.name
                dist_data["name"] = pdf_to_docling.stem

                # 2. JSON 파일로 저장 (파일명에서 한글 제거)
                # 정규식을 사용하여 파일 시스템용 안전한 이름 생성
                safe_stem = re.sub(r'[^a-zA-Z0-9_]', '_', pdf_to_docling.stem)
                if not safe_stem.strip('_'): # 만약 이름 전체가 한글이라 비어버린다면
                    safe_stem = f"doc_{int(time.time())}"
                
                extract_path = extract_dir / f"output_result_{safe_stem}.json"
                
                with open(extract_path, "w", encoding="utf-8") as f:
                    json.dump(dist_data, f, ensure_ascii=False, indent=2)

                print(f"JSON 파일 저장 완료: {extract_path.absolute()}")
                return dist_data

        except Exception as e:
            print(f"오류 발생: {pdf_to_docling.name} / {e}")
            return None
        finally:
            # [핵심] GPU와 CPU 메모리를 강제로 비움
            if 'conv_result' in locals(): del conv_result
            del converter 
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()

    def parse(self,pdf_path: str, output_dir: dict[str, Any]) -> list[dict[str, Any]]:
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
        docling_data = self.extract(pdf_path=pdf_path, output_dir=extract_dir)
        if not docling_data:
            return None
        chunks = process_document(pdf_path=pdf_path, asset_root=asset_dir, data=docling_data)
        output_path = Path(struct_dir) / f"{Path(pdf_path).stem}.jsonl"
        save_jsonl(chunks, output_path)
        return chunks

    @staticmethod
    def _split_by_heading(markdown: str) -> list[str]:
        """## 헤딩 기준으로 섹션을 분리합니다."""
        import re
        parts = re.split(r"(?=^## )", markdown, flags=re.MULTILINE)
        return parts if len(parts) > 1 else [markdown]