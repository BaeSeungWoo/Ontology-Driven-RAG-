from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz


def sanitize_filename(value: str | None) -> str:
    """파일 시스템에서 사용 불가한 문자를 제거 후 파일 명 반환
    만약 문자열이 없거나 제거 후 빈 문자열이 될 시 'unknown_document' 반환

    Args:
        value (str | None) : 파일 명 (문자열 또는 None)
    
    Returns:
        str : 정규화된 파일 명
    
    Examples:
        >>> sanitize_filename("Hello World")
        'hello_world'
        >>> sanitize_filename("Hello World! 123")
        'hello_world_123'
    """
    if not value:
        return "unknown_document"
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", value).strip().rstrip(".")
    return sanitized or "unknown_document"


def get_document_asset_root(data: dict[str, Any], asset_root: str | Path) -> Path:
    """문서별로 asset 목록을 나누기 위하여 문서 이름으로 된 폴더 경로 생성
    
    Args:
        data (dict[str, any]): load 된 Docling 추출물 데이터
        asset_root (str | Path): asset 루트 폴더 경로 

    Returns:
        Path : 문서별 asset 저장 경로
    """
    document_name = data.get("name")
    return Path(asset_root) / sanitize_filename(document_name)


def make_asset_path(kind: str, ref: str, data: dict[str, Any], asset_root: str | Path, ref_id_fn) -> str | None:
    """Docling 추출물에서 뽑아낸 id를 통하여 이미지, 테이블 실 저장 경로 생성
    
    item_id를 해당 저장할 이름으로 선정
    `get_document_asset_root` 함수를 통하여 실제로 저장될 루트 경로 가져옴.

    Args:
        kind (str): data 타입(picture, table)
        ref (str): data 참조 경로
        data (dict[str, Any]): load 된 Docling 추출물 데이터
        asset_root (str | Path): asset 루트 폴더 경로
        ref_id_fn: ref_id 생성 함수
        
    Returns:
        str: 이미지, 테이블 실 저장 경로

    Examples:
        >>> type == picture
            /project/assets/pictures/0.png
        >>> type == table
            /project/assets/tables/0.md
    """
    item_id = ref_id_fn(ref)
    if not item_id:
        return None
    document_asset_root = get_document_asset_root(data, asset_root)
    if kind == "pictures":
        return (document_asset_root / "pictures" / f"{item_id}.png").as_posix()
    if kind == "tables":
        return (document_asset_root / "tables" / f"{item_id}.md").as_posix()
    if kind == "groups":
        return (document_asset_root / "groups" / f"{item_id}.json").as_posix()
    return None


def get_picture_render_payload(
    picture_node: dict[str, Any],
    doc: fitz.Document
) -> dict[str, Any] | None:
    """Docling 이미지 노드를 기반으로 PDF 렌더링에 필요한 메타데이터(클립 영역)를 생성

    이미지의 식별자 추출, 목차 페이지 필터링, 그리고 좌표계 변환(Origin 처리)을 수행하여
    최종적으로 PyMuPDF에서 사용할 수 있는 Rect 객체를 포함한 딕셔너리를 반환

    Args:
        picture_node (dict[str, Any]): Docling에서 추출된 이미지 노드 데이터.
        doc (fitz.Document): 분석 중인 원본 PDF 문서 객체.

    Returns:
        dict[str, Any] | None: 렌더링에 필요한 정보들(ref, id, page 객체, rect 영역 등).
            유효한 좌표 정보가 없거나 영역이 비어있으면 None을 반환.
    """
    picture_ref = picture_node.get("self_ref")
    picture_id = picture_ref.split("/")[-1]
    prov = picture_node.get("prov", [])

    p_info = prov[0]
    page_no = p_info.get("page_no", 1)
    bbox = p_info.get("bbox", {})
    origin = bbox.get("coord_origin", "TOPLEFT")

    page_index = page_no - 1
    if page_index < 0 or page_index >= len(doc):
        return None

    l = bbox.get("l")
    t = bbox.get("t")
    r = bbox.get("r")
    b = bbox.get("b")
    if None in (l, t, r, b):
        return None

    page = doc[page_index]
    page_height = page.rect.height

    if origin == "BOTTOMLEFT":
        y0 = page_height - t
        y1 = page_height - b
    else:
        y0 = t
        y1 = b

    x0 = min(l, r)
    x1 = max(l, r)
    y0, y1 = min(y0, y1), max(y0, y1)
    rect = fitz.Rect(x0, y0, x1, y1) & page.rect
    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return None

    return {
        "picture_ref": picture_ref,
        "picture_id": picture_id,
        "page": page,
        "rect": rect
    }


def analyze_picture_policy(
    picture_node: dict[str, Any],
    pdf_path: str | Path,
    picture_render_scale: float,
    small_picture_max_width: int,
    small_picture_max_height: int,
) -> dict[str, Any]:
    """PDF 내 이미지들의 크기와 렌더링 가능 여부에 따라 추출 여부 반환
    
        각 이미지 노드를 가상으로 렌더링 후 실제 픽셀 크기를 측정하고

        기준치 미달인 소형 이미지는 추출 X

    Args:
        data (dict[str, Any]): Docling 문서 데이터 (이미지 노드 목록 포함).
        pdf_path (str | Path): 이미지 크기를 측정할 원본 PDF 파일 경로.
        picture_render_scale (float): 크기 측정을 위한 렌더링 배율 (DPI 조절용).
        small_picture_max_width (int): 소형 이미지로 간주할 최대 가로 픽셀 값.
        small_picture_max_height (int): 소형 이미지로 간주할 최대 세로 픽셀 값.

    Returns:
        dict[str, dict[str, Any]]: 이미지 참조(self_ref)를 키로 하는 정책 정보 딕셔너리.
            포함 값: {should_export, is_small, width, height}
    """
    picture_policy: dict[str, Any] = {}

    with fitz.open(pdf_path) as doc:
        payload = get_picture_render_payload(picture_node, doc)
        if not payload:
            picture_policy = {
                "should_export": False,
                "is_small": False,
                "width": None,
                "height": None,
            }

        try:
            pix = payload["page"].get_pixmap(
                matrix=fitz.Matrix(picture_render_scale, picture_render_scale),
                clip=payload["rect"],
            )
        except Exception:
            picture_policy = {
                "should_export": False,
                "is_small": False,
                "width": None,
                "height": None,
            }

        width = pix.width
        height = pix.height
        is_small = width <= small_picture_max_width and height <= small_picture_max_height
        picture_policy = {
            "should_export": not is_small,
            "is_small": is_small,
            "width": width,
            "height": height,
        }
            

    return picture_policy

def build_table_grid(table_node: dict[str, Any]) -> list[list[str]]:
    """테이블 형태를 세팅
    
    몇 행 몇 열에 어떤 텍스트가 배치될 지 결정

    Args:
        table_node (dict[str, Any]): Docling에서 추출된 테이블 데이터

    Returns:
        list[list[str]]: 텍스트로 채워진 2차원 리스트. 
            데이터가 없거나 크기가 유효하지 않으면 빈 리스트([])를 반환
    """
    table_cells = table_node.get("data", {}).get("table_cells", [])
    if not table_cells:
        return []

    max_row = max((cell.get("start_row_offset_idx", 0) for cell in table_cells), default=-1)
    max_col = max((cell.get("start_col_offset_idx", 0) for cell in table_cells), default=-1)
    if max_row < 0 or max_col < 0:
        return []

    grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for cell in sorted(table_cells, key=lambda cell: (cell.get("start_row_offset_idx", 0), cell.get("start_col_offset_idx", 0))):
        row_idx = cell.get("start_row_offset_idx", 0)
        col_idx = cell.get("start_col_offset_idx", 0)
        grid[row_idx][col_idx] = " ".join(str(cell.get("text", "")).split())

    return grid


def escape_markdown_table_cell(value: str) -> str:
    """마크다운 테이블 구조를 유지하기 위해 특수문자를 변환
    
    열 구분자로 사용되는 파이프(|) 기호 앞에 \를 추가하고,
    셀 내에서 허용되지 않는 줄바꿈 문자를 <br> 태그로 치환.

    Args:
        value (str): 마크다운 테이블 셀에 삽입할 문자열

    Returns:
        str: 마크다운 문법에 맞춘 정제된 문자열

    Examples:
        >>> # 파이프 기호가 포함된 경우
        >>> escape_markdown_table_cell("Option A | Option B")
            'Option A \\| Option B'
        >>> # 줄바꿈이 포함된 경우
        >>> escape_markdown_table_cell("Line 1\\nLine 2")
            'Line 1<br>Line 2'
    """
    return value.replace("|", r"\|").replace("\n", "<br>")


def serialize_table_markdown(
    table_node: dict[str, Any]
) -> str:
    """Docling 테이블 데이터를 실제 마크다운 언어로 변환 하여 테이블을 표현

    `build_table_grid`로 데이터를 그리드 형태로 재구성 한 후,
    `escape_markdown_table_cell`로 마크다운 문법에 맞게 수정하여 
    마크다운 테이블 문법으로 반환 

    Args:
        table_node (dict[str, Any]): Docling에서 추출된 테이블 데이터

    Returns:
        str: 직렬화된 마크다운 테이블 문자열, 없을 시 빈 문자열 반환

    Examples:
        >>> # grid가 [['Name', 'Age'], ['Alice', '30']]인 경우
        >>> print(serialize_table_markdown(node, build_fn, escape_fn))
            | Name  | Age |
            | ---   | --- |
            | Alice | 30  |
    """
    grid = build_table_grid(table_node)
    if not grid:
        return ""

    escaped_rows = [[cell.replace("|", r"\|").replace("\n", "<br>") for cell in row] for row in grid]
    header = escaped_rows[0]
    separator = ["---"] * len(header)
    body_rows = escaped_rows[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body_rows)
    return "\n".join(lines)


def serialize_table_text(
    table_node: dict[str, Any]
) -> str:
    """Docling 테이블 데이터를 문자열로 표현

    기존 표 구조를 유지하는 것이 아닌 
    각 행 어떤 열에 데이터가 들어있는 지 직관적으로 나열함.
    
    Args:
        table_node (dict[str, Any]): Docling에서 추출된 테이블 데이터

    Returns:
        str: 행 별로 요약된 문자열, 없을 시 빈 문자열 반환

    Examples:
        >>> R0 | C0: 이름   | C1: 나이
        >>> R1 | C0: 김철수 | C1: 25

    """
    table_data = table_node.get("data", {})
    cells = sorted(table_data.get("table_cells", []), key=lambda cell: (cell.get("start_row_offset_idx", 0), cell.get("start_col_offset_idx", 0)))
    if not cells:
        return ""

    rows: dict[int, list[str]] = {}
    for cell in cells:
        row_idx = cell.get("start_row_offset_idx", 0)
        col_idx = cell.get("start_col_offset_idx", 0)
        cell_text = " ".join(str(cell.get("text", "")).split())
        if cell_text:
            rows.setdefault(row_idx, []).append(f"C{col_idx}: {cell_text}")

    lines = []
    for row_idx in sorted(rows):
        lines.append(f"R{row_idx} | " + " | ".join(rows[row_idx]))
    return "\n".join(lines)

def serialize_picture_text(
    picture_node: dict[str, Any],
    indexes: dict[str, dict[str, dict[str, Any]]],
    ref_kind_fn,
) -> str:
    """이미지 노드와 연결된 캡션·자식 텍스트를 하나의 문자열로 직렬화한다.

    Args:
        picture_node (dict[str, Any]): 이미지 노드 데이터.
        indexes (dict[str, dict[str, dict[str, Any]]]): self_ref 조회 인덱스.
        ref_kind_fn: ref 종류 판별 함수.

    Returns:
        str: 중복 제거 후 줄바꿈으로 연결한 이미지 관련 텍스트.
    """
    texts: list[str] = []

    for ref_list_name in ("captions", "children"):
        for child_ref in picture_node.get(ref_list_name, []):
            ref = child_ref.get("$ref")
            kind = ref_kind_fn(ref)

            if kind == "texts":
                node = indexes["texts"].get(ref)
                value = (node or {}).get("text", "").strip()
                if value:
                    texts.append(value)

            elif kind == "groups":
                group_node = indexes["groups"].get(ref)
                for group_child in (group_node or {}).get("children", []):
                    group_child_ref = group_child.get("$ref")
                    if ref_kind_fn(group_child_ref) == "texts":
                        text_node = indexes["texts"].get(group_child_ref)
                        value = (text_node or {}).get("text", "").strip()
                        if value:
                            texts.append(value)

    picture_text = "\n".join(dict.fromkeys(texts))
    return picture_text


def export_table_assets(
    table_node: dict[str, Any],
    asset_path: str | Path,
) -> bool:
    """테이블 노드를 마크다운 파일로 저장한다.

    테이블 데이터를 마크다운 문자열로 직렬화한 뒤, 지정된 경로에 파일로 기록한다.
    직렬화 결과가 비어 있으면 저장하지 않고 실패로 처리한다.

    Args:
        table_node (dict[str, Any]): Docling에서 추출된 테이블 노드.
        asset_path (str | Path): 저장할 마크다운 파일 경로.

    Returns:
        int: 저장 성공 시 ``True``, 실패 시 ``False``.
    """
    output_path = Path(asset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    table_markdown = serialize_table_markdown(table_node)
    if not table_markdown:
        return False

    with output_path.open("w", encoding="utf-8") as f:
        f.write(table_markdown)
    return True


def export_picture_assets(
    picture_node: dict[str, Any],
    pdf_path: str | Path,
    asset_path: str | Path,
    picture_render_scale: float,
) -> bool:
    """이미지 노드를 PDF에서 렌더링하여 지정된 경로에 저장한다.

    이미지 노드의 bbox 정보를 바탕으로 PDF 페이지의 해당 영역을 잘라 렌더링하고,
    결과 이미지를 지정된 파일 경로에 저장한다. 렌더링 정보 계산이나 저장에 실패하면
    ``False`` 를 반환한다.

    Args:
        picture_node (dict[str, Any]): Docling에서 추출된 이미지 노드.
        pdf_path (str | Path): 원본 PDF 파일 경로.
        asset_path (str | Path): 저장할 이미지 파일 경로.
        picture_render_scale (float): 렌더링 배율.

    Returns:
        bool: 저장 성공 시 ``True``, 실패 시 ``False``.
    """
    output_path = Path(asset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with fitz.open(pdf_path) as doc:
        payload = get_picture_render_payload(picture_node, doc)
        if not payload:
            return False

        try:
            pix = payload["page"].get_pixmap(
                matrix=fitz.Matrix(picture_render_scale, picture_render_scale),
                clip=payload["rect"],
            )
            pix.save(output_path)
            return True
        except Exception as e:
            print("error", e)
            return False
