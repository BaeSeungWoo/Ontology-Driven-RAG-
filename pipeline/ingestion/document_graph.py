"""Publish one page/table graph per shared manual, with a machine-to-document catalog."""
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re

from bs4 import BeautifulSoup
from pipeline.ingestion.paddleocr_import import write_generated
from pipeline.ingestion.prepared_documents import document_key


def sync_graph(root, destination, chunks):
    documents = defaultdict(list)
    for row in chunks:
        if row["page_content"].strip() and row["metadata"]["document_type"] in {"manual", "controller"}:
            documents[document_key(row["metadata"]["source_doc_name"])].append(row)
    folder = destination / "graph"
    catalog_file = folder / "catalog.json"
    old = json.loads(catalog_file.read_text(encoding="utf8")) if catalog_file.is_file() else {}
    previous_files = {name: key for key, name in old.get("documents", {}).items()}
    revisions = {}
    catalog = {}
    machines = defaultdict(list)
    for rows in documents.values():
        meta = rows[0]["metadata"]
        name = meta["source_doc_name"]
        stamp = sha256()
        for row in rows:
            m = row["metadata"]
            asset = Path(m.get("asset_path") or "")
            asset_stamp = None
            if asset.suffix.lower() == ".html" and "asset" in asset.parts:
                asset_stamp = root.joinpath(*asset.parts[asset.parts.index("asset"):]).stat().st_mtime_ns
            stamp.update(json.dumps([row["page_content"], m.get("section_title"), m.get("page_range"),
                                     m.get("container_type"), str(asset), asset_stamp]).encode())
        revision = stamp.hexdigest()
        revisions[name] = revision
        previous = previous_files.get(name)
        if previous and old.get("revisions", {}).get(name) == revision and (folder / "documents" / (previous + ".json")).is_file():
            catalog[previous] = name
            for code in meta["machine_code"]:
                machines[code].append(previous)
            continue
        pages, tables = {}, []
        for row in rows:
            m = row["metadata"]
            match = re.match(r"\d+", str(m.get("page_range", "")))
            if not match:
                raise ValueError(f"그래프의 페이지 정보 누락: {row['id']}")
            num = int(match[0])
            page = pages.setdefault(num, {"page": num, "blocks": [], "titles": []})
            label = m.get("section_title", "")
            if label and label not in page["titles"]:
                page["titles"].append(label)
            if m.get("container_type") == "tables":
                table = dict(page=num, label=label, content=row["page_content"])
                asset = Path(m.get("asset_path") or "")
                if asset.suffix.lower() == ".html" and "asset" in asset.parts:
                    path = root.joinpath(*asset.parts[asset.parts.index("asset"):])
                    html = BeautifulSoup(path.read_text(encoding="utf-8-sig"), "html.parser")
                    table["rows"] = [[dict(text=c.get_text(" ", strip=True), rowspan=int(c.get("rowspan",1)),
                                           colspan=int(c.get("colspan",1))) for c in tr.find_all(["td","th"], recursive=False)]
                                     for tr in html.select("tr")]
                tables.append(table)
            else:
                page["blocks"].append(row["page_content"])
        name = meta["source_doc_name"]
        payload = json.dumps(dict(document=name, pages=list(pages.values()), tables=tables), ensure_ascii=False).encode()
        ident = sha256(payload).hexdigest()
        write_generated(folder / "documents" / (ident + ".json"), payload)
        catalog[ident] = name
        for code in meta["machine_code"]:
            machines[code].append(ident)
    write_generated(catalog_file, json.dumps(dict(documents=catalog, machines=machines, revisions=revisions), ensure_ascii=False).encode())
    for path in (folder / "documents").glob("*.json"):
        if re.fullmatch("[a-f0-9]{64}", path.stem) and path.stem not in catalog:
            path.unlink()
