import json
import re
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF


def extract_part_number(path: Path) -> int:
    """분할된 PDF 명시 부분 추출
    
    Args:
        path (Path): 대상 경로
    
    Returns:
        int: part 명시 번호
            예: part_1 -> 1
                part_2 -> 2
    """
    match = re.search(r"part_(\d+)", path.name)
    if not match:
        raise ValueError(f"part 번호를 찾을 수 없습니다: {path}")
    return int(match.group(1))


def extract_page_number(path: Path) -> int:
    """배치 순번 추출

    Args:
        path (Path): 대상 경로

    Returns:
        int: 배치 순번 번호 
            예: 1~10 페이지 -> 0
                11~20 페이지 -> 1
    """
    match = re.match(r"(\d+)_", path.name)
    if not match:
        raise ValueError(f"배치 순번을 찾을 수 없습니다: {path}")
    return int(match.group(1))


def load_json_file(json_path: Path) -> dict[str, Any]:
    """JSON 파일 로드

    Args:
        json_path (Path): JSON 파일 경로

    Returns:
        dict[str, Any]: JSON -> 파이썬 딕셔너리 형태
    """
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_pdf_page_count(pdf_path: Path) -> int:
    """PDF 페이지 수 반환
    
    Args:
        pdf_path (Path): PDF 파일 경로

    Returns:
        int: PDF 파일 페이지 수
    """
    doc = fitz.open(str(pdf_path))
    try:
        return len(doc)
    finally:
        doc.close()


def merge_one_pdf_json(
    pdf_name_dir: Path,
    split_pdf_root_dir: Path,
    output_file: Path,
) -> None:
    """분할된 PDF에서 추출한 JSON들을 기준으로 element들을 병합

    PDF 파일의 각 part로서 저장된 json을 하나로 병합한다.

    Args:
        pdf_name_dir (Path): 각 파트별 JSON 파일 저장 경로
        split_pdf_root_dir: 원본 PDF 명으로 만들어진 폴더 이름 경로
        output_file: 병합 결과 저장 경로
    """
    combined_elements: list[dict[str, Any]] = []
    merged_files: list[str] = []
    current_page_offset = 0

    part_dirs = sorted(
        [path for path in pdf_name_dir.iterdir() if path.is_dir() and path.name.startswith("part_")],
        key=extract_part_number,
    )

    if not part_dirs:
        print(f"part 폴더가 없습니다: {pdf_name_dir}")
        return

    for part_dir in part_dirs:
        part_number = extract_part_number(part_dir)
        part_pdf_path = split_pdf_root_dir / pdf_name_dir.name / f"part_{part_number}.pdf"

        if not part_pdf_path.exists():
            raise FileNotFoundError(f"분할 PDF 파일이 없습니다: {part_pdf_path}")

        json_files = sorted(part_dir.glob("*.json"), key=extract_page_number)

        for json_file in json_files:
            data = load_json_file(json_file)
            merged_files.append(str(json_file))

            elements = data.get("elements", [])
            for element in elements:
                merged_element = dict(element)

                if "page" in merged_element and isinstance(merged_element["page"], int):
                    merged_element["page"] = merged_element["page"] + current_page_offset

                combined_elements.append(merged_element)

        current_page_offset += get_pdf_page_count(part_pdf_path)

    result_data = {
        "total_elements": len(combined_elements),
        "total_pages": current_page_offset,
        "merged_files": merged_files,
        "elements": combined_elements,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    print(f"병합 완료: {output_file}")


def merge_all_pdf_jsons(
    batch_json_root_dir: Path,
    split_pdf_root_dir: Path,
    merged_output_dir: Path,
) -> None:
    """분할된 PDF에서 추출된 JSON 파일들이 모여있는 폴더들을 순회하면서 

    `merge_one_pdf_json`을 실행하여 병합 결과를 저장함

    batch_json_root_dir (Path): 병합할 JSON을 찾는 기준 경로
    split_pdf_root_dir (Path): 각 파트 별 PDF가 몇 페이지 인지 찾는 기준 루트
    merged_output_dir (Path): 최종 병합 결과 저장 경로
    """
    pdf_name_dirs = sorted([path for path in batch_json_root_dir.iterdir() if path.is_dir()])

    if not pdf_name_dirs:
        print(f"병합할 PDF 폴더가 없습니다: {batch_json_root_dir}")
        return

    for pdf_name_dir in pdf_name_dirs:
        output_file = merged_output_dir / f"{pdf_name_dir.name}.json"

        merge_one_pdf_json(
            pdf_name_dir=pdf_name_dir,
            split_pdf_root_dir=split_pdf_root_dir,
            output_file=output_file,
        )
