"""Import the inspected per-page PaddleOCR export without re-OCR or PDF access."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile

from pipeline.ingestion.chunk_refiner import ChunkRefiner
from pipeline.ingestion.prepared_documents import document_catalog, document_key


def long_path(path: Path) -> Path:
    path = path.resolve()
    if os.name == "nt" and not str(path).startswith("\\\\?\\"):
        return Path("\\\\?\\" + str(path))
    return path


def preserve_write(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(f"기존 파일과 내용이 다릅니다. 덮어쓰지 않습니다: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)


def import_zip(archive: Path, root: Path, source_type: str = "paddleocr") -> None:
    if source_type not in {"paddleocr", "docling"}:
        raise ValueError(source_type)
    destination = long_path(root / "inputs/extracted" / source_type)
    with zipfile.ZipFile(archive) as bundle:
        planned = []
        seen = set()
        for info in bundle.infolist():
            if info.is_dir():
                continue
            relative = PurePosixPath(info.filename)
            if relative.is_absolute() or any(p in {"..", "."} or ":" in p or "\\" in p for p in relative.parts):
                raise ValueError(f"잘못된 ZIP 경로: {info.filename}")
            parts = relative.parts
            # Keep the ZIP's document layout. Preserve each delivery's manifest.
            if parts == ("_reports", "manifest.json"):
                suffix = hashlib.sha256(bundle.read(info)).hexdigest()[:12]
                parts = ("_reports", f"manifest-{suffix}.json")
            target = destination.joinpath(*parts).resolve()
            if not target.is_relative_to(destination) or target in seen:
                raise ValueError(f"중복 또는 외부 ZIP 경로: {info.filename}")
            seen.add(target)
            if target.exists():
                with bundle.open(info) as source, target.open("rb") as existing:
                    if hashlib.file_digest(source, "sha256").digest() != hashlib.file_digest(existing, "sha256").digest():
                        raise FileExistsError(f"기존 추출물을 덮어쓰지 않습니다: {target}")
            planned.append((info, target))
        for info, target in planned:
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(info) as source, target.open("xb") as output:
                shutil.copyfileobj(source, output)


def jsonl(rows):
    return ("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)).encode("utf-8")


def prepare_paddleocr(root: Path, machines: dict, *, docling_documents=()) -> dict:
    source = long_path(root / "inputs/extracted/paddleocr")
    catalog = document_catalog(machines)
    documents = sorted(p for p in source.iterdir() if p.is_dir() and p.name != "_reports") if source.exists() else []
    if not documents:
        raise FileNotFoundError(f"PaddleOCR 결과가 없습니다: {source}")
    from pipeline.ingestion.extraction_manifests import load_manifests
    declared = load_manifests(source)
    plans, skipped = [], []
    for folder in documents:
        source_name = folder.name
        page_prefix = folder.name
        key = document_key(folder.name)
        if key not in catalog:
            aliases = [item for item in declared.values()
                       if item["folder"].endswith(" ")
                       and item["folder"].rstrip(" ") + "_" == folder.name]
            if len(aliases) == 1:
                source_name = aliases[0]["document"]
                page_prefix = aliases[0]["folder"]
                key = document_key(source_name)
        if key not in catalog:
            raise ValueError(f"machine_info에 연결되지 않은 문서: {folder.name}")
        entry = catalog[key]
        if entry["document_type"] not in {"manual", "controller"} or key in docling_documents:
            skipped.append({"document": folder.name, "type": entry["document_type"]})
            continue
        results = folder
        pages = {}
        for path in results.glob("*_res.json"):
            match = re.fullmatch(r"(.+)_(\d+)_res\.json", path.name)
            if not match or " ".join(match[1].split()) != " ".join(page_prefix.split()):
                raise ValueError(f"페이지 번호를 판별할 수 없습니다: {path}")
            number = int(match[2]) + 1  # JSON page_index may restart in each OCR batch.
            if number in pages:
                raise ValueError(f"중복 페이지: {path}")
            pages[number] = path
        expected = declared.get(key, {}).get("original_pdf_pages", max(pages, default=0))
        if not pages or set(pages) != set(range(1, expected + 1)):
            raise ValueError(f"페이지 누락 또는 범위 오류: {folder.name}")
        plans.append((folder, source_name, entry, pages, hashlib.sha256(key.encode()).hexdigest()[:20]))
    if not plans:
        raise ValueError("변환할 manual PaddleOCR 결과가 없습니다.")
    report = {"documents": [], "skipped": skipped}
    for folder, source_name, entry, pages, ident in plans:
        raw, assets, missing = [], {}, []
        for page, path in sorted(pages.items()):
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            section = ""
            blocks = data["parsing_res_list"]
            for position, block in enumerate(blocks):
                label = block["block_label"]
                text = block["block_content"].strip()
                bbox = block["block_bbox"]
                if label in {"doc_title", "paragraph_title"}:
                    section = text
                kind = "tables" if label == "table" else "pictures" if label in {"image", "chart"} else "texts"
                asset = ""
                prefix = f"p{page:04d}-b{position:04d}"
                if kind == "pictures":
                    name = "img_in_" + label + "_box_" + "_".join(str(int(v)) for v in bbox) + ".jpg"
                    image = path.parent / "imgs" / f"p{page - 1}_{name}"
                    if not image.is_file():
                        image = path.parent / "imgs" / name
                    if image.is_file():
                        asset = f"{root.name}/asset/paddleocr/{ident}/{prefix}.jpg"
                        assets[root.parent / asset] = image.read_bytes()
                    else:
                        missing.append({"page": page, "block": position, "image": name})
                elif kind == "tables" and text:
                    asset = f"{root.name}/asset/paddleocr/{ident}/{prefix}.md"
                    assets[root.parent / asset] = text.encode("utf-8")
                raw.append({"chunk_id": f"paddle:{ident}:p{page:04d}:b{position:04d}", "text": text,
                            "metadata": {"source": {"doc_name": source_name},
                                         "pages": {"range": f"{page}-{page}"},
                                         "section": {"title": section},
                                         "container": {"type": kind, "asset_path": asset},
                                         "ocr": {"bbox": bbox, "block_label": label,
                                                 "width": data["width"], "height": data["height"]}}})
        # Retain all blocks for page context; omit page furniture from retrieval.
        searchable = [r for r in raw if r["metadata"]["ocr"]["block_label"] not in
                      {"number", "header", "footer", "header_image", "footer_image", "footnote", "aside_text"}]
        chunks = ChunkRefiner().convert(searchable)
        for chunk in chunks:
            chunk["metadata"].update(entry)
            chunk["metadata"].update(site_id=root.name, source_type="paddleocr")
        outputs = {root / "struct" / f"{ident}.jsonl": jsonl(raw),
                   root / "struct/documents" / f"paddleocr-{ident}.jsonl": jsonl(chunks), **assets}
        # Check the entire document before publishing any of its outputs.
        for target, content in outputs.items():
            if target.exists() and target.read_bytes() != content:
                raise FileExistsError(f"기존 변환 결과를 덮어쓰지 않습니다: {target}")
        for target, content in outputs.items():
            preserve_write(target, content)
        report["documents"].append({"document": folder.name, "pages": len(pages), "chunks": len(chunks),
                                    "assets": len(assets), "machines": entry["machine_code"],
                                    "missing_images": missing})
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8")
    report_id = hashlib.sha256(payload).hexdigest()[:12]
    preserve_write(root / f"struct/reports/paddleocr-{report_id}.json", payload)
    return report
