import json
from typing import Any
from pathlib import Path
from collections import defaultdict 
import re

from refs import ref_kind, ref_id, build_indexes, collect_refs, resolve_ref
from toc import get_toc_map, detect_toc_pages, get_section_from_toc, filter_toc_pages
from assets import make_asset_path, serialize_table_text, serialize_picture_text, analyze_picture_policy, export_picture_assets, export_table_assets

TEXT_LABELS_TO_INCLUDE = {
    "section_header",
    "text",
    "list_item",
    "caption",
    "footnote",
    "formula",
    "code",
    "checkbox_selected",
    "checkbox_unselected",
}

TEXT_LABELS_TO_SKIP = {"page_header", "page_footer"}
TOC_SCAN_PAGES = 45
TOC_MIN_SCORE = 5
PICTURE_RENDER_SCALE = 3.0
SMALL_PICTURE_MAX_WIDTH = 90
SMALL_PICTURE_MAX_HEIGHT = 90

INPUT_DIR = Path("input_json_dir")
OUTPUT_DIR = Path("output_json_dir")
PDF_DIR = Path(r"C:\Users\seung\WAFF\2026_업체\AI가치사슬\RAG\참고파일\from 성민씨\화낙 30,31,32 모델B")
ASSET_ROOT = Path("chunk_assets")

PDF_MAP = {
    "parameter": "파라미터설명서_B-64490EN_05_FS30i31i32i-B Parameter",
    "maintenance": "보수설명서_B-64485EN_02_FS30i31i32i-B Maintenance",
    "machining_center_op": "취급설명서(MCT)_B-64484EN-2_05_FS30i31i32i-B Machining Center_OP",
    "lathe_op": "취급설명서(선반)_B-64484EN-1_05_FS30i31i32i-B Lathe_OP",
    "description": "사양설명서_B-64482EN_05_FS30i31i32i-B Descriptions",
    "connection_hardware": "결합설명서(HARDWARE)_B-64483EN_02_FS30i31i32i-B Connection(Hardware)",
    "connection_function": "결합설명서(FUNCTION)_B-64483EN-1_05_FS30i31i32i-B Connection(Function)",
    "common_op": "취급설명서(공통)_B-64484EN_05_FS30i31i32i-B Common_OP",
    "B-65285EN_04_alpha_i_Mainternance": "B-65285EN_04_alpha_i_Mainternance",
    "B-65325EN_02": "B-65325EN_02",
    "B-65395EN_01_IO Link Option beta_i-AMP": "B-65395EN_01_IO Link Option beta_i-AMP"
}

def get_pages_from_prov(prov: list[dict[str, Any]] | None) -> list[int]:
    """prov 배열에서 중복 없는 페이지 번호 목록을 추출한다.
    
    Args:
        prov (list[dict[str, Any]]): Docling 노드의 prov(실제) 데이터

    Returns:
        list[int]: 추출된 페이지 번호 리스트
    """
    if not prov:
        return []
    pages: list[int] = []
    for item in prov:
        page_no = item.get("page_no")
        if isinstance(page_no, int):
            pages.append(page_no)
    return sorted(set(pages))

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

def process_document(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Docling 문서 1건을 처리하여 최종 chunk 목록을 생성한다.

    문서 본문의 ref를 평탄화한 뒤, 각 노드에 대해 페이지 정보와 섹션 정보를 계산하고
    텍스트/테이블/이미지 타입에 따라 내용을 정규화하거나 에셋을 저장한다.
    마지막으로 생성된 unit들을 섹션과 컨테이너 기준으로 병합하여 최종 chunk 목록을 반환한다.

    Args:
        data (dict[str, Any]): Docling JSON 문서 데이터.

    Returns:
        list[dict[str, Any]]: 문서에서 생성된 최종 chunk 목록.
    """
    idx_data = build_indexes(data=data)

    ref_datas = []
    body = data['body']
    for ref in body["children"]:
        child_ref = ref.get("$ref")
        if child_ref:
            collect_refs(child_ref, idx_data, ref_datas)

    # 원본 문서 이름 매핑 및 목차 판별
    pdf_name = PDF_MAP.get(data['name'])+".pdf"
    toc_map = get_toc_map(pdf_path=PDF_DIR / pdf_name)
    toc_pages = detect_toc_pages(
        pdf_path=PDF_DIR / pdf_name, 
        scan_pages=TOC_SCAN_PAGES, 
        min_score=TOC_MIN_SCORE
    )

    # 각 청크를 담을 배열
    node_data = []
    for ref in ref_datas:
        # 인덱스에 해당하는 데이터 가져오기
        idx = resolve_ref(ref=ref, indexes=idx_data)
        if not idx:
            continue

        # 페이지 설정
        page_metadata = {"start": None, "end": None}
        prov = idx.get("prov") or []

        # 목차로 판단된 페이지 거름
        pages = filter_toc_pages(pages=get_pages_from_prov(prov=prov), toc_pages=toc_pages)
        if not pages:
            continue
        else:
            page_metadata = {
                "start": min(pages),
                "end": max(pages),
            }

        kind = ref_kind(idx.get("self_ref"))

        # pictures, tables의 경우 asset_path 설정
        asset_path = make_asset_path(
            kind=kind, 
            ref=idx.get("self_ref"), 
            data=data, 
            asset_root=ASSET_ROOT,
            ref_id_fn=ref_id
        )

        if kind == "texts":
            # 해당 라벨 조건에 따라 추출 할 지 안 할지 선택
            label = idx.get("label")
            if label in TEXT_LABELS_TO_SKIP or label not in TEXT_LABELS_TO_INCLUDE:
                continue

            text_value = idx.get("text") or idx.get("orig") or ""
        elif kind == "tables":
            # 테이블 저장
            table_exported = export_table_assets(table_node=idx, asset_path=asset_path)

            if not table_exported:
                continue
            
            # 테이블 텍스트 정규화
            text_value = serialize_table_text(table_node=idx)
        elif kind == "pictures":
            # 이미지 추출 정책 
            picture_policy = analyze_picture_policy(
                picture_node=idx, 
                pdf_path=PDF_DIR / pdf_name,
                picture_render_scale=PICTURE_RENDER_SCALE,
                small_picture_max_width=SMALL_PICTURE_MAX_WIDTH,
                small_picture_max_height=SMALL_PICTURE_MAX_HEIGHT)

            if picture_policy['is_small']:
                continue
            
            # 이미지 저장
            picture_exported = export_picture_assets(
                picture_node=idx,
                pdf_path=PDF_DIR / pdf_name,
                asset_path=asset_path,
                picture_render_scale=PICTURE_RENDER_SCALE,
            )

            if not picture_exported:
                continue
            
            # 이미지 딸린 텍스트 정규화
            text_value = serialize_picture_text(picture_node=idx, indexes=idx_data, ref_kind_fn=ref_kind)
        else:
            text_value = idx.get("text") or ""


        # toc_map에서 섹션 추출
        section = get_section_from_toc(pages=pages, toc_map=toc_map)

        metadata = {
            "source": {"doc_name": PDF_MAP.get(data["name"])},
            "section": section,
            "pages": page_metadata,
            "container": {"type": kind, "asset_path": asset_path},
        }

        node = {
            "chunk_id": data["name"] + idx.get("self_ref", ""),
            "text": text_value,
            "metadata": metadata
        }
        node_data.append(node)
    
    # 청크들을 목차에 따라 합침
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

def build_chunks(
    json_dir: str | Path = INPUT_DIR, 
    output_dir: str | Path = OUTPUT_DIR
) -> None:
    """입력 디렉터리의 Docling JSON 파일들을 순회하며 chunk JSONL 파일을 생성한다.

    각 입력 문서에 대해 ``process_document`` 를 실행하고, 결과 chunk 목록을
    출력 디렉터리에 동일한 파일명 기반의 ``.jsonl`` 파일로 저장한다.

    Args:
        json_dir (str | Path): 입력 JSON 파일들이 있는 디렉터리.
        output_dir (str | Path): 생성된 JSONL 파일을 저장할 디렉터리.

    Returns:
        None
    """
    json_paths=sorted(Path(json_dir).glob("*.json"))
    for json_path in json_paths:
        with Path(json_path).open("r", encoding="utf-8") as f:
            data = json.load(f)
            chunks = process_document(data)
            output_path = Path(output_dir) / f"{Path(json_path).stem}.jsonl"
            save_jsonl(chunks, output_path)
