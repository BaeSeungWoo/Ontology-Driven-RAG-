# pipeline/parsers/docling_parser.py
#
# 일반 텍스트 기반 PDF 매뉴얼 파싱 전략
# Docling: 레이아웃 인식 + 표·제목 구조 보존

import time
import json
import re
import shutil
import tempfile
import fitz
import io
import gc
from pathlib import Path
from typing import Any
from tqdm import tqdm

from doclings.merge_json import merge_docling_jsons

from doclings.generate_chunks import process_document, save_jsonl
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.accelerator_options import AcceleratorOptions
from docling.datamodel.base_models import ConversionStatus, InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode
from docling.datamodel.base_models import DocumentStream

class DoclingParser:
    """
    Docling 기반 일반 매뉴얼 파서.
    표·제목·단락 구조를 보존하면서 Markdown 형태로 변환합니다.

    설치: pip install docling
    """

    def __init__(self):
        pass

    def _create_converter(self) -> DocumentConverter:
        """호출될 때마다 새로운 DocumentConverter 객체를 생성합니다."""
        pipeline_options = PdfPipelineOptions(
            accelerator_options=AcceleratorOptions(
                device="cpu",
                num_threads=8
            ),
            do_ocr = False,
        )
        pipeline_options.table_structure_options.mode = TableFormerMode.FAST 
        pdf_option = PdfFormatOption(pipeline_options=pipeline_options)

        return DocumentConverter(
            format_options={InputFormat.PDF: pdf_option}
        )

    def _extract(self, pdf_path: str | Path, output_dir: str | Path, batch_size: int = 300) -> tuple[Path, str]:
        """특정 폴더에 존재하는 PDF 목록들을 Docling을 통하여 JSON 형태의 파일로 내보낸다.

        batch_size를 기준으로 페이지 수를 분할하여 추출을 진행한다.
        
        파일 명의 경우 반드시 영어, 숫자, _으로만 구성될 수 있으며,
        한글, 특수 문자 등 파일 시스템 상 안전하지 않은 문자가 들어가 있을 경우
        docling 라이브러리 내부에서 오류를 내보내므로 주의

        출력 JSON은 batch_dir/원본 문서명_part_xxx.json 형태로 출력된다.

        Args:
            pdf_path (str): 추출할 PDF 폴더 경로
            output_dir (str): Docling 추출물 결과들이 저장될 폴더 경로
            batch_size (int = 300): 분할할 pdf 페이지 수 
        
        Returns:
            예) docling_result.json 
        """
        pdf_to_docling = Path(pdf_path)
        extract_dir = Path(output_dir)

        src_doc = fitz.open(pdf_to_docling)
        total_pages = src_doc.page_count

        pdf_name = pdf_to_docling.stem

        batch_dir = extract_dir / "batch_json" / pdf_name
        batch_dir.mkdir(parents=True, exist_ok=True)

        page_steps = list(range(0, total_pages, batch_size))

        converter = self._create_converter()

        with tqdm(total=len(page_steps), desc=f" > {pdf_name}", leave=True) as pbar:
            for start in page_steps:
                end = min(start + batch_size, total_pages)

                temp_pdf = fitz.open()
                temp_pdf.insert_pdf(src_doc, from_page=start, to_page=end-1)
                pdf_bytes = temp_pdf.write()

                stream = io.BytesIO(pdf_bytes)
                source = DocumentStream(name=f"{pdf_name}_part_{start}", stream=stream)

                try:
                    # 2. Docling 변환
                    result = converter.convert(source)
                    
                    if result.status == ConversionStatus.SUCCESS:
                        # 3. 보정 없이 즉시 딕셔너리 변환 및 저장
                        dist_data = result.document.export_to_dict()
                        
                        # 파일명 규칙: 원본명_part_인덱스.json
                        part_idx = start // batch_size
                        output_file = batch_dir / f"{pdf_name}_part_{part_idx:03d}.json"
                        
                        with open(output_file, "w", encoding="utf-8") as f:
                            json.dump(dist_data, f, ensure_ascii=False, indent=2)
                        
                        # 객체 명시적 삭제로 RAM 확보
                        del dist_data
                        del result
                except Exception as e:
                    print(f"\n[부분 실패] {start}~{end-1}p: {e}")
                finally:
                    # 리소스 정리
                    temp_pdf.close()
                    stream.close()
                    gc.collect()
                    pbar.update(1)

        src_doc.close()
        return batch_dir, pdf_name

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
        batch_dir, pdf_name = self._extract(pdf_path=pdf_path, output_dir=extract_dir)
        docling_data = merge_docling_jsons(batch_dir, pdf_name)
        if not docling_data:
            return None
        chunks = process_document(pdf_path=pdf_path, asset_root=asset_dir, data=docling_data)
        output_path = Path(struct_dir) / f"{Path(pdf_path).stem}.jsonl"
        save_jsonl(chunks, output_path)
        return chunks