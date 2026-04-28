from __future__ import annotations

import json
import re
from typing import Any
from pathlib import Path
from collections import defaultdict 
from assets import make_asset_path, export_table_assets, serialize_table_text, analyze_picture_policy, export_picture_assets

TEXT_LABELS_TO_SKIP = {"header", "footer"}

def build_caption_map(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """caption을 (category, asset_id) 기준으로 연결한다.

    Returns:
        dict[tuple[str, int], str]:
            예: {("table", 18): "표 1.4 ...", ("figure", 35): "그림 2.1 ..."}
    """
    caption_map: dict[tuple[str, int], str] = {}
    used_targets: set[tuple[str, int]] = set()

    def find_next_same_page(idx: int, category: str, page: int) -> tuple[str, int] | None:
        for j in range(idx + 1, len(elements)):
            e = elements[j]
            if e.get("page") != page:
                break
            if e.get("category") == category:
                key = (category, int(e["id"]))
                if key not in used_targets:
                    return key
        return None

    def find_prev_same_page(idx: int, category: str, page: int) -> tuple[str, int] | None:
        for j in range(idx - 1, -1, -1):
            e = elements[j]
            if e.get("page") != page:
                break
            if e.get("category") == category:
                key = (category, int(e["id"]))
                if key not in used_targets:
                    return key
        return None

    for idx, element in enumerate(elements):
        if element.get("category") != "caption":
            continue

        caption_text = element.get("content", {}).get("text", "").strip()
        if not caption_text:
            continue

        page = element.get("page")

        target: tuple[str, int] | None = None
        if caption_text.startswith("표"):
            target = find_next_same_page(idx, "table", page)
            if target is None:
                target = find_prev_same_page(idx, "table", page)

        elif caption_text.startswith("그림"):
            target = find_prev_same_page(idx, "figure", page)
            if target is None:
                target = find_next_same_page(idx, "figure", page)

        if target is None:
            continue

        caption_map[target] = caption_text
        used_targets.add(target)

    return caption_map

def slugify_section(value: str | None) -> str:
    """섹션 제목을 chunk_id용 슬러그 문자열로 변환한다.

    영문자와 숫자를 제외한 문자는 ``-`` 로 치환하고, 양끝의 구분자는 제거한다.
    값이 없거나 변환 결과가 비어 있으면 기본값으로 ``"no-section"`` 을 반환한다.

    Args:
        value (str | None): 원본 섹션 제목.

    Returns:
        str: chunk_id에 사용하기 적합한 슬러그 문자열.
    """
    if not value:
        return "no-section"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return slug or "no-section"

def container_key(container: dict[str, Any]) -> tuple[str | None, str | None]:
    """컨테이너 비교를 위한 불변 키를 생성한다.

    컨테이너의 타입과 asset 경로를 묶어 동일 컨테이너 여부를 비교할 수 있는
    튜플 형태의 키를 반환한다.

    Args:
        container (dict[str, Any]): 컨테이너 메타데이터.

    Returns:
        tuple[str | None, str | None]: ``(type, asset_path)`` 형태의 비교용 키.
    """
    return (container.get("type"), container.get("asset_path"))

def chunk_units_by_section_and_container(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """연속된 unit들을 섹션과 컨테이너 기준으로 묶어 최종 chunk로 변환한다.

    같은 섹션과 같은 컨테이너에 속한 연속 unit들을 하나의 chunk로 합치고,
    텍스트는 줄바꿈으로 연결한다. 각 chunk에는 대표 source, section, pages,
    container 메타데이터와 고유한 chunk_id를 함께 구성한다.

    Args:
        units (list[dict[str, Any]]): unit 단위로 정리된 중간 결과 목록.

    Returns:
        list[dict[str, Any]]: 섹션/컨테이너 기준으로 병합된 최종 chunk 목록.
    """
    final_chunks: list[dict[str, Any]] = []
    current_units: list[dict[str, Any]] = []
    current_texts: list[str] = []
    current_section_raw: str | None = None
    current_container_key: tuple[str | None, str | None] | None = None
    chunk_index: dict[tuple[str, tuple[str | None, str | None]], int] = defaultdict(int)

    def flush() -> None:
        nonlocal current_units, current_texts, current_section_raw, current_container_key
        if not current_units:
            return

        first = current_units[0]["metadata"]
        section = first["section"]
        container = first["container"]
        section_key = section.get("raw") or "NO_TOC"
        group_key = (section_key, container_key(container))
        chunk_index[group_key] += 1

        page_numbers: list[int] = []
        for unit in current_units:
            pages = unit["metadata"]["pages"]
            start = pages.get("start")
            end = pages.get("end")
            if start is not None and end is not None:
                page_numbers.extend(range(start, end + 1))

        asset_path = container.get("asset_path")
        asset_id = slugify_section(Path(asset_path).stem) if asset_path else "no-asset"

        page_metadata = {"range": ""}

        if page_numbers:
            page_metadata = {
                "range": f"{min(page_numbers)}-{max(page_numbers)}"
            }


        final_chunks.append(
            {
                "chunk_id": f"{slugify_section(section.get('title'))}:{container.get('type')}:{asset_id}:{chunk_index[group_key]:04d}",
                "text": "\n\n".join(current_texts).strip(),
                "metadata": {
                    "source": first["source"],
                    "section": {
                        "title": section.get("title"),
                        "level": section.get("level"),
                    },
                    "pages": page_metadata,
                    "container": container,
                },
            }
        )

        current_units = []
        current_texts = []
        current_section_raw = None
        current_container_key = None

    for unit in units:
        unit_text = unit.get("text", "").strip()
        if not unit_text:
            continue

        unit_section_raw = unit["metadata"]["section"].get("raw")
        unit_container_key = container_key(unit["metadata"]["container"])

        if current_units and (
            unit_section_raw != current_section_raw or unit_container_key != current_container_key
        ):
            flush()

        if not current_units:
            current_section_raw = unit_section_raw
            current_container_key = unit_container_key

        current_units.append(unit)
        current_texts.append(unit_text)

    flush()
    return final_chunks

def process_document(data: dict[str, Any], asset_dir: str | Path, pdf_path: str | Path) -> list[dict[str, Any]]:
    doc_name = pdf_path.stem

    elements = data["elements"]

    node_data = []

    caption_map = build_caption_map(elements=elements)
    for element in elements:
        category = element["category"]
        kind = ""
        asset_path = make_asset_path(element=element, asset_root=asset_dir, doc_name=doc_name)
        # category = "caption"일 경우 테이블 또는 이미지에 어떻게 포함을 시킬 지 생각
        if category in TEXT_LABELS_TO_SKIP or category == "caption":
            continue
        elif category == "table":
            kind = "tables"
            # 테이블 저장로직 설정
            table_exported = export_table_assets(table_node=element, asset_path=asset_path)

            if not table_exported:
                continue
            text_value = serialize_table_text(table_node=element)
            text_value = text_value.replace("![image](/image/placeholder)", "")
            text_value = text_value.strip()

            caption = caption_map.get(("table", int(element["id"])))
            if caption:
                text_value = f"{caption}\n\n{text_value}" if text_value else caption
        elif category == "figure":
            kind = "pictures"
            picture_policy = analyze_picture_policy(
                picture_node=element, 
                pdf_path=pdf_path)

            if picture_policy['is_small']:
                continue
            # 이미지 저장로직 설정
            picture_exported = export_picture_assets(
                picture_node=element,
                pdf_path=pdf_path,
                asset_path=asset_path
            )
            if not picture_exported:
                continue
            text_value = element["content"]["text"]
            text_value = text_value.replace("![image](/image/placeholder)", "")
            text_value = text_value.strip()

            caption = caption_map.get(("figure", int(element["id"])))
            if caption:
                text_value = f"{caption}\n\n{text_value}" if text_value else caption
        else:
            kind = "texts"
            # 텍스트 저장로직 설정
            text_value = element["content"]["text"]

        page = element["page"]

        metadata = {
            "source": {"doc_name": doc_name},
            "section": {"title": None, "level": None, "raw": None},
            "pages": {"start": page, "end": page},
            "container": {"type": kind, "asset_path": asset_path}
        }

        node = {
            "chunk_id": f"{doc_name}_{kind}_{element['id']}",
            "text": text_value,
            "metadata": metadata
        }
        node_data.append(node)

    final_chunks = chunk_units_by_section_and_container(node_data)
    return final_chunks

def save_jsonl(chunks: list[dict[str, Any]], output_path: str | Path) -> None:
    """생성된 chunk 목록을 JSONL 파일로 저장한다.

    Args:
        chunks (list[dict[str, Any]]): 저장할 chunk 목록.
        output_path (str | Path): 출력 JSONL 파일 경로.

    Returns:
        None
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")