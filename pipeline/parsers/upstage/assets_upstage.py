import fitz

from typing import Any
from pathlib import Path

PICTURE_RENDER_SCALE = 3.0
SMALL_PICTURE_MAX_WIDTH = 120
SMALL_PICTURE_MAX_HEIGHT = 120

def make_asset_path(element: dict[str, Any], asset_root: str | Path, doc_name: str) -> str | None:
    """테이블, 이미지에 대한 실 저장 경로 생성

    item_id로 해당 파일에 대한 이름 결정

    `asset_root`, `doc_name`을 통하여 실제로 저장될 루트 경로 생성
    
    Args:
        element (dict[str, Any]) : upstage 데이터
        asset_root (str | Path): asset 루트 폴더 경로
        doc_name (str): 실 문서 이름

    Returns:
        str : 테이블, 이미지 실 저장 경로
    """
    item_id = f"{element['id']}"
    kind = element["category"]
    if isinstance(item_id, str) and item_id.strip() == "":
        return None
    document_asset_root = Path(asset_root) / doc_name
    if kind == "figure":
        return (document_asset_root / "pictures" / f"{item_id}.png").as_posix()
    if kind == "table":
        return (document_asset_root / "tables" / f"{item_id}.md").as_posix()
    return None

def to_norm_coords(coords: Any) -> list[float]:
    """upstage 데이터의 좌표 객체를 받아 좌표 리스트 형태로 반환

    Args:
        coords (Any): 좌표 객체 ([{"x":..,"y":..}, ...])

    Returns:
        list[float] : [x1, y1, x2, y2, ...]
    """
    if not coords:
        raise ValueError("coordinates is empty")

    # case 1: list[dict]
    if isinstance(coords, list) and isinstance(coords[0], dict):
        norm_coords = []
        for p in coords:
            if "x" not in p or "y" not in p:
                raise ValueError(f"invalid point: {p}")
            norm_coords.extend([float(p["x"]), float(p["y"])])
        return norm_coords

    # case 2: flat list
    if isinstance(coords, list) and all(isinstance(v, (int, float)) for v in coords):
        if len(coords) % 2 != 0:
            raise ValueError("flat coordinates length must be even")
        return [float(v) for v in coords]

    raise ValueError(f"unsupported coordinates format: {type(coords)}")

def get_picture_render_payload(picture_node: dict[str, Any], doc: fitz.Document) -> dict[str, Any] | None:
    """Upstage 이미지 노드를 기반으로 PDF 렌더링에 필요한 메타데이터(클립 영역)를 생성

    이미지의 식별자 추출 및 좌표계 변환을 수행하여 
    최종적으로 PyMuPDF에서 사용할 수 있는 Rect 객체를 포함한 딕셔너리를 반환

    Args:
        picture_node (dict[str, Any]): Upstage에서 추출된 이미지 노드 데이터.
        doc (fitz.Document): 분석 중인 원본 PDF 문서 객체.

    Returns:
        dict[str, Any] | None: 렌더링에 필요한 정보들(id, page 객체, rect 영역 등).
            유효한 좌표 정보가 없거나 영역이 비어있으면 None을 반환.
    """
    picture_id = f"{picture_node['id']}"
    page_index = picture_node["page"] - 1
    page = doc[page_index]
    page_width = page.rect.width
    page_height = page.rect.height

    real_coords = []
    norm_coords = to_norm_coords(picture_node["coordinates"])
    for i in range(len(norm_coords)):
        if i % 2 == 0: # X 좌표 (짝수 인덱스)
            real_coords.append(norm_coords[i] * page_width)
        else:          # Y 좌표 (홀수 인덱스)
            real_coords.append(norm_coords[i] * page_height)
            
    # 3. 변환된 좌표로 사각형(Rect) 생성
    xs = real_coords[0::2]
    ys = real_coords[1::2]
    rect = fitz.Rect(min(xs), min(ys), max(xs), max(ys))
    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
        return None

    return {
        "picture_id": picture_id,
        "page": page,
        "rect": rect
    }

def analyze_picture_policy(
    picture_node: dict[str, Any], 
    pdf_path: str | Path, 
    picture_render_scale: float = PICTURE_RENDER_SCALE, 
    small_picture_max_width: int = SMALL_PICTURE_MAX_WIDTH, 
    small_picture_max_height: int = SMALL_PICTURE_MAX_HEIGHT) -> dict[str, Any]:
    """PDF 내 이미지들의 크기와 렌더링 가능 여부에 따라 추출 여부 반환
    
        각 이미지 노드를 가상으로 렌더링 후 실제 픽셀 크기를 측정하고

        기준치 미달인 소형 이미지는 추출 X

    Args:
        data (dict[str, Any]): Upstage 이미지 노드.
        pdf_path (str | Path): 이미지 크기를 측정할 원본 PDF 파일 경로.
        picture_render_scale (float): 크기 측정을 위한 렌더링 배율 (DPI 조절용).
        small_picture_max_width (int): 소형 이미지로 간주할 최대 가로 픽셀 값.
        small_picture_max_height (int): 소형 이미지로 간주할 최대 세로 픽셀 값.

    Returns:
        dict[str, Any] : 정책 정보 딕셔너리.
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

def export_picture_assets(picture_node: dict[str, Any], pdf_path: str | Path, asset_path: str | Path, picture_render_scale: float = PICTURE_RENDER_SCALE) -> bool:
    """이미지 노드를 PDF에서 렌더링하여 지정된 경로에 저장한다.

    이미지 노드의 coordinates 정보를 바탕으로 PDF 페이지의 해당 영역을 잘라 렌더링하고,
    결과 이미지를 지정된 파일 경로에 저장한다. 렌더링 정보 계산이나 저장에 실패하면
    ``False`` 를 반환한다.

    Args:
        picture_node (dict[str, Any]): Upstage에서 추출된 이미지 노드.
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

def export_table_assets(table_node: dict[str, Any], asset_path: str | Path) -> bool:
    """테이블 노드를 마크다운 파일로 저장한다.

    테이블 데이터를 마크다운 문자열로 직렬화한 뒤, 지정된 경로에 파일로 기록한다.
    직렬화 결과가 비어 있으면 저장하지 않고 실패로 처리한다.

    Args:
        table_node (dict[str, Any]): Upstage에서 추출된 테이블 노드.
        asset_path (str | Path): 저장할 마크다운 파일 경로.

    Returns:
        int: 저장 성공 시 ``True``, 실패 시 ``False``.
    """
    output_path = Path(asset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    table_text = table_node["content"]["text"]

    table_markdown = table_text.replace("\r\n", "\n").replace("\r", "\n").replace("![image](/image/placeholder)", "").strip()
    if not table_markdown:
        return False

    with output_path.open("w", encoding="utf-8") as f:
        f.write(table_markdown)
    return True

def serialize_table_text(table_node: dict[str, Any]) -> str:
    """Upstage 테이블 데이터를 문자열로 표현

    기존 표 구조를 유지하는 것이 아닌 
    각 행 어떤 열에 데이터가 들어있는 지 직관적으로 나열함.
    
    Args:
        table_node (dict[str, Any]): Upstage에서 추출된 테이블 데이터

    Returns:
        str: 행 별로 요약된 문자열, 없을 시 빈 문자열 반환

    Examples:
        >>> R0 | C0: 이름   | C1: 나이
        >>> R1 | C0: 김철수 | C1: 25
    """
    table_text = table_node.get("content", {}).get("text", "")
    if not table_text:
        return ""

    if "![image](/image/placeholder)" in table_text:
        return table_text

    rows = []
    for line in table_text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("|") and "---" in line:
            continue
        if "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if parts and parts[0] == "":
            parts = parts[1:]
        if parts and parts[-1] == "":
            parts = parts[:-1]

        cell_texts = []
        for col_idx, cell_text in enumerate(parts):
            cell_text = " ".join(cell_text.split())
            if cell_text:
                cell_texts.append(f"C{col_idx}: {cell_text}")

        if cell_texts:
            rows.append(cell_texts)

    lines = []
    for row_idx, row_cells in enumerate(rows):
        lines.append(f"R{row_idx} | " + " | ".join(row_cells))
    return "\n".join(lines)
