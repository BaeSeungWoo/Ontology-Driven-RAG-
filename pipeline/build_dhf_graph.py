"""Build page and table nodes from the same DHF manual OCR blocks used by RAG."""
import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "pipeline/data/yunam_origin/scanned/chunks/documents.jsonl"
OUTPUT = ROOT / "backend/data/graph_indexes/yunam_origin/M005/dhf8000.json"
DOCUMENT = "연암3(DHF8000, DHF8000 #2) DN SOLUTIONS DHF series 조작설명서 965p"


def build():
    pages, tables = {}, []
    with SOURCE.open(encoding="utf8") as stream:
        for line in stream:
            row = json.loads(line)
            meta = row["metadata"]
            if meta["source_doc_name"] != DOCUMENT:
                continue
            number = int(meta["pdf_page"])
            page = pages.setdefault(number, {"page": number, "blocks": [], "titles": []})
            content = row["page_content"].strip()
            if not content:
                continue
            if meta["block_label"] in ("paragraph_title", "doc_title"):
                page["titles"].append(content)
            if meta["container_type"] == "tables":
                table = dict(page=number, content=content, label=meta["section_title"])
                asset = Path(meta.get("asset_path", ""))
                if asset.suffix == ".html" and "asset" in asset.parts:
                    path = SOURCE.parents[1].joinpath(*asset.parts[asset.parts.index("asset"):])
                    if path.is_file():
                        html = BeautifulSoup(path.read_text(encoding="utf8"), "html.parser")
                        table["rows"] = [[dict(text=cell.get_text("\n", strip=True),
                                               rowspan=int(cell.get("rowspan", 1)), colspan=int(cell.get("colspan", 1)))
                                          for cell in tr.find_all(["td", "th"], recursive=False)] for tr in html.select("tr")]
                tables.append(table)
            else:
                page["blocks"].append(content)
    if not pages:
        raise ValueError(f"Missing OCR for {DOCUMENT}")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=OUTPUT.parent, mode="w", encoding="utf8", delete=False) as out:
        json.dump(dict(document=DOCUMENT, pages=list(pages.values()), tables=tables), out, ensure_ascii=False)
    Path(out.name).replace(OUTPUT)
    print(f"{len(pages)} pages, {len(tables)} tables")


if __name__ == "__main__":
    build()
