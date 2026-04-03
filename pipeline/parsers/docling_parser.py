# pipeline/parsers/docling_parser.py
#
# 일반 텍스트 기반 PDF 매뉴얼 파싱 전략
# Docling: 레이아웃 인식 + 표·제목 구조 보존

import time
from pathlib import Path
import json
from typing import List
import torch

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.accelerator_options import AcceleratorDevice, AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from langchain_core.documents import Document

class DoclingParser:
    """
    Docling 기반 일반 매뉴얼 파서.
    표·제목·단락 구조를 보존하면서 Markdown 형태로 변환합니다.

    설치: pip install docling torch
    """

    def __init__(self):
        # torch를 통하여 GPU 사용 가능성 검증
        # GPU 사용 시 batch_size 추가
        if torch.cuda.is_available():
            pipeline_options = PdfPipelineOptions(
                accelerator_options=AcceleratorOptions(
                    device=AcceleratorDevice.CUDA
                ),
                ocr_batch_size = 8, # VRAM이 크므로 높여도 되지만, 에러 방지를 위해 적당히 유지
                layout_batch_size = 32, # 레이아웃 분석 배치
                do_ocr = False, # 텍스트 기반 PDF라면 False 유지
            )

            pdf_option = PdfFormatOption(pipeline_options=pipeline_options)
        else:
            pdf_option = PdfFormatOption(
                pipeline_options=PdfPipelineOptions(
                    do_ocr = False # 텍스트 기반 PDF라면 False 유지
                )
            )

        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=pdf_option
                )
            }
        )

    def extract(self, input_path: str, docling_output_path: str):
        """특정 폴더에 존재하는 PDF 목록들을 Docling을 통하여 JSON 형태의 파일로 내보낸다.

        파일 명의 경우 반드시 영어, 숫자, _으로만 구성될 수 있으며,
        한글, 특수 문자 등 파일 시스템 상 안전하지 않은 문자가 들어가 있을 경우
        docling 라이브러리 내부에서 오류를 내보내므로 주의

        출력 JSON은 output_result_xxx.json 형태로 출력된다.

        Args:
            input_path (str): 추출할 PDF 폴더 경로
            docling_output_path (str): Docling 추출물 결과들이 저장될 폴더 경롷
        
        """
        # 입력 경로 설정
        input_dir = Path(input_path)

        # JSON 저장 폴더
        output_dir = Path(docling_output_path)
        output_dir.mkdir(parents=True, exist_ok=True)

        pdf_files = sorted(list(input_dir.glob("*.pdf")) + list(input_dir.glob("*.PDF")))

        if not pdf_files:
            print(f"{input_dir} 폴더에 PDF 파일이 없습니다")
            return

        start_time = time.time()
        self.converter.initialize_pipeline(InputFormat.PDF)
        init_runtime = time.time() - start_time
        print(f"Pipeline initialized in {init_runtime:.2f} seconds.")

        for pdf_path in pdf_files:
            try:
                start_time = time.time()
                conv_result = self.converter.convert(pdf_path)
                pipeline_runtime = time.time() - start_time

                if conv_result.status != ConversionStatus.SUCCESS:
                    print(f"변환 실패: {pdf_path.name}")
                    continue

                num_pages = len(conv_result.pages)
                print(f"Document converted in {pipeline_runtime:.2f} seconds.")
                print(f"  {num_pages / pipeline_runtime:.2f} pages/second.")

                # 1. 결과를 딕셔너리 형태로 변환
                dist_data = conv_result.document.export_to_dict()

                # 2. JSON 파일로 저장
                output_path = output_dir / f"output_result_{pdf_path.stem}.json"
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(dist_data, f, ensure_ascii=False, indent=2)

                print(f"JSON 파일이 성공적으로 저장되었습니다: {output_path.absolute()}")
            except Exception as e:
                print(f"오류 발생: {pdf_path.name} / {e}")

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