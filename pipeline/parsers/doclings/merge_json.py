from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

# part_xxx 형태의 정규식
PART_RE = re.compile(r"_part_(\d+)\.json$", re.IGNORECASE)

# #/section/index 형태의 정규식
REF_RE = re.compile(r"^#/(?P<section>[^/]+)/(?P<index>\d+)$")

def sort_key(path: Path) -> tuple[int, str]:
    """JSON 파일 정렬 키 반환

    파일명에 `_part_숫자.json` 패턴이 포함되어 있으면 해당 숫자를 기준으로
    정렬, 패턴이 없으면 큰 값을 부여.
    같은 순번이면 파일명 자체를 보조 정렬 기준으로 사용.

    Args:
        path (Path): JSON 파일 경로.

    Returns:
        tuple[int, str]: 파트 번호와 파일명으로 구성된 정렬용 튜플.
    
    """
    match = PART_RE.search(path.name)
    if match:
        return (int(match.group(1)), path.name)
    return (10**9, path.name)


def load_json(path: Path) -> dict[str, Any]:
    """JSON 파일을 읽어 딕셔너리로 반환.

    UTF-8 인코딩으로 파일을 열고 JSON 데이터를 파싱.

    Args:
        path (Path): JSON 파일 경로.

    Returns:
        dict[str, Any]: JSON 파일 내용을 파싱한 딕셔너리 객체
    """
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def shift_ref(ref: str, ref_offsets: dict[str, int]) -> str:
    """참조 문자열의 인덱스를 section별 offset만큼 이동.

    `#/section/index` 형식의 참조 문자열을 해석하여, 같은 section에 대해
    미리 계산된 offset을 index에 더한 새 참조 문자열을 생성.
    형식이 맞지 않는 문자열은 그대로 반환.

    Args:
        ref (str): 참조 문자열.
        ref_offsets (dict[str, int]): section 이름을 키로 하고, 해당 section에 더할
            인덱스 offset을 값으로 가지는 딕셔너리.

    Returns:
        str: offset이 반영된 새 참조 문자열 또는 원본 참조 문자열.
    """
    match = REF_RE.match(ref)
    if not match:
        return ref

    section = match.group("section")
    index = int(match.group("index"))
    offset = ref_offsets.get(section, 0)
    return f"#/{section}/{index + offset}"


def rewrite_refs_and_pages(obj: Any, ref_offsets: dict[str, int], page_offset: int) -> Any:
    """중첩된 JSON 구조에서 참조와 페이지 번호를 재귀적으로 보정한다.

    딕셔너리와 리스트를 재귀적으로 순회하면서 `$ref`, `self_ref`,
    `page_no` 필드를 찾아 값을 수정한다.
    `$ref`와 `self_ref`는 section별 offset을 반영해 변경하고,
    `page_no`는 page_offset만큼 증가시킨다.

    Args:
        obj (Any): 보정할 대상 객체이다. dict, list, 원시 타입이 모두 올 수 있다.
        ref_offsets (dict[str, Any]): section별 참조 인덱스 보정값을 담은 딕셔너리이다.
        page_offset (int): 페이지 번호에 더할 오프셋이다.

    Returns:
        Any : 참조와 페이지 번호가 보정된 새 객체이다.
    """
    if isinstance(obj, dict):
        new_obj = {}
        for key, value in obj.items():
            if key in {"$ref", "self_ref"} and isinstance(value, str):
                new_obj[key] = shift_ref(value, ref_offsets)
            elif key == "page_no" and isinstance(value, int):
                new_obj[key] = value + page_offset
            else:
                new_obj[key] = rewrite_refs_and_pages(value, ref_offsets, page_offset)
        return new_obj

    if isinstance(obj, list):
        return [rewrite_refs_and_pages(item, ref_offsets, page_offset) for item in obj]

    return obj


def merge_pages(merged: dict[str, Any], incoming: dict[str, Any], page_offset: int) -> None:
    """incoming 문서의 페이지 정보를 merged 문서에 병합한다.

    incoming의 `pages` 항목을 순회하면서 페이지 키와 내부 `page_no`를
    page_offset만큼 증가시켜 merged의 `pages`에 추가한다.
    각 페이지 내부에 포함된 참조와 페이지 번호도 함께 재작성한다.

    Args:
        merged (dict[str, Any]): 병합 결과가 누적되는 대상 문서 딕셔너리이다.
        incoming (dict[str, Any]): 새로 병합할 원본 문서 딕셔너리이다.
        page_offset (int): 기존 페이지와 충돌하지 않도록 더할 페이지 번호 오프셋이다.

    """
    merged_pages = merged.setdefault("pages", {})
    incoming_pages = incoming.get("pages", {})

    if not isinstance(merged_pages, dict) or not isinstance(incoming_pages, dict):
        return

    for key, page in incoming_pages.items():
        old_page_no = int(key)
        new_page_no = old_page_no + page_offset
        new_page = rewrite_refs_and_pages(copy.deepcopy(page), {}, page_offset)
        new_page["page_no"] = new_page_no
        merged_pages[str(new_page_no)] = new_page

def merge_docling_jsons(input_dir: str | Path, pdf_name: str) -> dict[str, Any]:
    """여러 Docling JSON 파일을 하나의 JSON으로 병합한다.

    입력 디렉터리의 JSON 파일들을 파트 순서에 맞게 정렬하여 읽은 뒤,
    첫 번째 문서를 기준으로 나머지 문서들의 list section, body/furniture의
    children, pages를 순차적으로 병합한다.
    이 과정에서 참조 인덱스와 페이지 번호가 충돌하지 않도록 offset을 적용한다.
    최종 병합 결과는 `{pdf_name}_merge.json` 파일로 저장된다.

    Args:
        input_dir (str | Path): 병합할 JSON 파일들이 들어 있는 디렉터리 경로이다.
        pdf_name (str): 결과 문서의 이름 및 출력 파일명 생성에 사용할 PDF 기준 이름이다.

    Returns:
        dict[str, Any] : 병합이 완료된 Docling JSON 딕셔너리이다.

    Raises:
        FileNotFoundError: 입력 디렉터리에 JSON 파일이 하나도 없을 때 발생한다.
    """
    input_dir = Path(input_dir)
    json_files = sorted(input_dir.glob("*.json"), key=sort_key)

    if not json_files:
        raise FileNotFoundError(f"No JSON files found in: {input_dir}")

    docs = [load_json(path) for path in json_files]
    merged = copy.deepcopy(docs[0])

    if "original_name" not in merged:
        merged["original_name"] = f"{pdf_name}.pdf"

    merged["name"] = pdf_name

    list_sections = {
        key for key, value in merged.items()
        if isinstance(value, list)
    }

    list_sections.discard("pages")

    current_max_page = 0
    if isinstance(merged.get("pages"), dict) and merged["pages"]:
        current_max_page = max(int(k) for k in merged["pages"].keys())

    for doc in docs[1:]:
        ref_offsets = {
            section: len(merged.get(section, []))
            for section in list_sections
        }
        page_offset = current_max_page

        for section in list_sections:
            incoming_items = doc.get(section, [])
            if not isinstance(incoming_items, list):
                continue

            rewritten_items = [
                rewrite_refs_and_pages(item, ref_offsets, page_offset)
                for item in incoming_items
            ]
            merged.setdefault(section, []).extend(rewritten_items)

        for container_key in ("body", "furniture"):
            incoming_container = doc.get(container_key)
            merged_container = merged.get(container_key)

            if (
                isinstance(incoming_container, dict)
                and isinstance(merged_container, dict)
                and isinstance(incoming_container.get("children"), list)
                and isinstance(merged_container.get("children"), list)
            ):
                merged_container["children"].extend(
                    rewrite_refs_and_pages(incoming_container["children"], ref_offsets, page_offset)
                )

        merge_pages(merged, doc, page_offset)

        if isinstance(merged.get("pages"), dict) and merged["pages"]:
            current_max_page = max(int(k) for k in merged["pages"].keys())

    output_path = input_dir / f"{pdf_name}_merge.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    return merged