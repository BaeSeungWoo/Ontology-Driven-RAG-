import fitz

from typing import Any
from pathlib import Path

PICTURE_RENDER_SCALE = 3.0
SMALL_PICTURE_MAX_WIDTH = 120
SMALL_PICTURE_MAX_HEIGHT = 120

def make_asset_path(element: dict[str, Any], asset_root: str | Path, doc_name: str) -> str | None:
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
    """
    반환 형식: [x1, y1, x2, y2, ...]
    입력 허용:
      1) [{"x":..,"y":..}, ...]
      2) [x1, y1, x2, y2, ...]
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
    picture_render_scale: float, 
    small_picture_max_width: int = SMALL_PICTURE_MAX_WIDTH, 
    small_picture_max_height: int = SMALL_PICTURE_MAX_HEIGHT) -> dict[str, Any]:
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
    output_path = Path(asset_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    table_text = table_node["content"]["text"]

    table_markdown = table_text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not table_markdown:
        return False

    with output_path.open("w", encoding="utf-8") as f:
        f.write(table_markdown)
    return True

def serialize_table_text(table_node: dict[str, Any]) -> str:
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
