"""Recover page context and asset links from prepared PaddleOCR blocks."""
from collections import defaultdict
from dataclasses import replace
from functools import lru_cache
import json
from pathlib import Path
import re


def origin_asset_path(path, site_id):
    if site_id == "yunam_origin" and isinstance(path, str) and path.startswith("yunam/"):
        return "yunam_origin/" + path[len("yunam/"):]
    return path


@lru_cache(maxsize=16)
def _pages(path: str, modified: int):
    pages = defaultdict(list)
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        row = json.loads(line)
        pages[row["metadata"]["pages"]["range"]].append(row)
    return pages


def _box(row):
    return row["metadata"]["ocr"]["bbox"]


def _distance(left, right):
    a, b = _box(left), _box(right)
    overlap = min(a[2], b[2]) - max(a[0], b[0])
    if overlap <= 0:
        return float("inf")
    return max(0, a[1] - b[3], b[1] - a[3])


def _picture_labels(rows):
    pictures = [r for r in rows if r["metadata"]["container"]["type"] == "pictures"]
    labels = defaultdict(list)
    for row in rows:
        if row["metadata"]["ocr"]["block_label"] not in {"figure_title", "vision_footnote"}:
            continue
        ranked = sorted(pictures, key=lambda picture: _distance(row, picture))
        # Ambiguous captions between two images must not be assigned arbitrarily.
        if ranked and _distance(row, ranked[0]) <= 150 and (
            len(ranked) == 1 or _distance(row, ranked[0]) < _distance(row, ranked[1])
        ):
            labels[ranked[0]["chunk_id"]].append(row["text"])
    for picture in pictures:
        box = _box(picture)
        # Small icons with no caption are not explanatory figures.
        if not labels[picture["chunk_id"]] and (box[2] - box[0] < 150 or box[3] - box[1] < 100):
            continue
        titles = [r for r in rows if (
            r["metadata"]["ocr"]["block_label"] in {"paragraph_title", "doc_title"}
            or (r["metadata"]["ocr"]["block_label"] == "text"
                and re.match(r"^\s*\(?\d+\)", r["text"]))
        ) and _box(r)[3] <= box[1] and _distance(r, picture) <= 250]
        if titles:
            title = min(titles, key=lambda r: _distance(r, picture))
            if not re.search(r"경고|주의|유의|위험|warning|caution|danger", title["text"], re.I):
                labels[picture["chunk_id"]].insert(0, "인접 절 제목: " + title["text"].splitlines()[0])
    return labels


def expand_paddle_pages(items, data_root: Path, site_id: str):
    expanded, seen = [], set()
    for item in items:
        meta = item.metadata
        match = re.fullmatch(r"paddle:([a-f0-9]+):p(\d+):.+", str(meta.get("chunk_id", "")))
        if meta.get("source_type") != "paddleocr" or not match:
            expanded.append(item)
            continue
        path = data_root / site_id / "struct" / (match[1] + ".jsonl")
        if not path.is_file():
            path = data_root / site_id / "scanned/struct" / (match[1] + ".jsonl")
        if not path.is_file():
            expanded.append(item)
            continue
        page = str(int(match[2]))
        key = (match[1], page)
        if key in seen:
            continue
        rows = _pages(str(path), path.stat().st_mtime_ns).get(f"{page}-{page}", [])
        rows = [r for r in rows if r["metadata"]["source"]["doc_name"] == meta["source_doc_name"]]
        if not rows:
            expanded.append(item)
            continue
        # Keep the original hit for unusually large pages instead of silently dropping text.
        if sum(len(r["text"]) for r in rows) > 6000:
            expanded.append(item)
            continue
        seen.add(key)
        labels = _picture_labels(rows)
        content, assets = [], []
        for row in rows:
            block = row["metadata"]
            kind = block["container"]["type"]
            if block["ocr"]["block_label"] in {"number", "header", "footer"}:
                continue
            if row["text"].strip():
                content.append(row["text"])
            label = " / ".join(labels.get(row["chunk_id"], []))
            if kind == "pictures" and not label:
                continue
            asset = origin_asset_path(block["container"].get("asset_path"), site_id)
            if kind not in {"pictures", "tables"} or not asset:
                continue
            target = (data_root / asset).resolve()
            if not target.is_relative_to(data_root.resolve()) or not target.is_file():
                continue
            assets.append({"asset_path": asset, "container_type": kind,
                           "label": label or block["section"]["title"], "source_chunk_id": row["chunk_id"]})
            if kind == "pictures":
                content.append("[연결된 그림의 제목·주석: " + label + "; 그림 내용 자체는 판독하지 않음]")
        ident = f"paddle:{match[1]}:page:{page}"
        expanded.append(replace(item, id=ident, text="\n\n".join(content), metadata={
            **meta, "chunk_id": ident, "container_type": "texts", "asset_path": "",
            "page_range": f"{page}-{page}", "context_scope": "ocr_page",
            "related_assets": assets, "source_block_ids": [r["chunk_id"] for r in rows],
        }))
    return expanded
