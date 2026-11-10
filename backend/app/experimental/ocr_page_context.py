"""Reading-order recovery used by experimental manual answers."""
from dataclasses import replace
from pathlib import Path
import re

from app.core.ocr_page_context import _box, _pages, _picture_labels, origin_asset_path


def order_page_rows(rows):
    """Restore vertical reading order only for an unambiguous single text column."""
    text_rows = [r for r in rows if r["metadata"]["ocr"]["block_label"] in {"text", "vision_footnote"}
                 and len(r["text"].strip()) >= 25]
    if not text_rows or max(_box(r)[0] for r in text_rows) >= min(_box(r)[2] for r in text_rows):
        return rows, False
    return sorted(rows, key=lambda r: (_box(r)[1], _box(r)[0])), True


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
        rows, ordered = order_page_rows(rows)
        seen.add(key)
        labels = _picture_labels(rows)
        content, assets = [], []
        sections = []
        for row in rows:
            block = row["metadata"]
            kind = block["container"]["type"]
            if block["ocr"]["block_label"] in {"number", "header", "footer"}:
                continue
            if row["text"].strip():
                content.append(row["text"])
                if ordered:
                    if block["ocr"]["block_label"] in {"paragraph_title", "doc_title"} or not sections:
                        sections.append({"title":row["text"] if block["ocr"]["block_label"] in {"paragraph_title", "doc_title"} else "",
                                         "text":""})
                    sections[-1]["text"] += row["text"] + "\n\n"
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
            "source_headers":[r["text"] for r in rows if r["metadata"]["ocr"]["block_label"] == "header"],
            **({"reading_order":"single_text_column", "ordered_sections":sections}
               if ordered else {}),
        }))
    return expanded
