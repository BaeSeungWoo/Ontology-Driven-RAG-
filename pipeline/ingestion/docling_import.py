"""Adapt exported Docling struct JSONL; do not reparse PDFs or batch JSON."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

from pipeline.ingestion.chunk_refiner import ChunkRefiner
from pipeline.ingestion.paddleocr_import import jsonl, long_path, preserve_write
from pipeline.ingestion.prepared_documents import document_catalog, document_key


def docling_documents(root: Path) -> dict:
    source = long_path(root / "inputs/extracted/docling")
    if not source.exists() or not any(source.iterdir()):
        return {}
    from pipeline.ingestion.extraction_manifests import load_manifests
    manifest = load_manifests(source, required=True)
    documents = {}
    for item in manifest.values():
        folder = item["folder"]
        if Path(folder).name != folder or folder in {".", ".."}:
            raise ValueError(f"잘못된 문서 폴더: {folder}")
        key = document_key(item["document"])
        if key in documents:
            raise ValueError(f"중복 Docling 문서: {key}")
        documents[key] = (source / folder, item)
    return documents


def prepare_docling(root: Path, machines: dict, documents: dict) -> dict:
    catalog = document_catalog(machines)
    report = {"documents": [], "skipped": []}
    for key, (folder, info) in documents.items():
        if key not in catalog:
            raise ValueError(f"machine_info에 연결되지 않은 문서: {info['document']}")
        entry = catalog[key]
        if entry["document_type"] not in {"manual", "controller"}:
            report["skipped"].append(info["document"])
            continue
        sources = list((folder / "struct").glob("*.jsonl"))
        if len(sources) != 1:
            raise ValueError(f"문서별 struct JSONL 1개가 필요합니다: {folder}")
        rows = [json.loads(line) for line in sources[0].read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        ident = hashlib.sha256(key.encode()).hexdigest()[:20]
        assets, ids = {}, set()
        repeated_ids = 0
        for position, row in enumerate(rows):
            original_id = row["chunk_id"]
            if original_id in ids:
                repeated_ids += 1
            ids.add(original_id)
            meta = row["metadata"]
            if meta["source"]["sha256"] != (info.get("source_pdf_sha256") or info.get("original_pdf_sha256")):
                raise ValueError(f"문서 SHA256 불일치: {sources[0]}")
            pages = re.fullmatch(r"(\d+)-(\d+)", meta["pages"]["range"])
            if not pages or not 1 <= int(pages[1]) <= int(pages[2]) <= info["pages"]:
                raise ValueError(f"잘못된 페이지 범위: {original_id}")
            # Export folder names may differ from the original document name.
            # The manifest + source hash establish the mapping, not fuzzy matching.
            meta["source"]["doc_name"] = Path(info["document"]).stem
            row["original_chunk_id"] = original_id
            # Some exports restart IDs in each section. Row position is stable in
            # the immutable input and keeps different pages from overwriting each other.
            row["chunk_id"] = f"docling:{ident}:b{position:06d}"
            asset = meta["container"].get("asset_path")
            if not asset:
                continue
            relative = asset.replace("\\", "/").rsplit("/asset/", 1)
            if len(relative) != 2:
                raise ValueError(f"지원하지 않는 자산 경로: {asset}")
            parts = PurePosixPath(relative[1]).parts
            if len(parts) != 3 or ".." in parts or parts[1] not in {"pictures", "tables"}:
                raise ValueError(f"잘못된 자산 경로: {asset}")
            original = (folder / "asset").joinpath(*parts)
            if not original.is_file():
                raise FileNotFoundError(f"Docling 자산 누락: {original}")
            target = f"{root.name}/asset/docling/{ident}/{parts[1]}/{parts[2]}"
            assets[root.parent / target] = original
            meta["container"]["asset_path"] = target
        chunks = ChunkRefiner().convert(rows)
        if not chunks:
            raise ValueError(f"빈 Docling 문서: {sources[0]}")
        for chunk in chunks:
            chunk["metadata"].update(entry)
            chunk["metadata"].update(site_id=root.name, source_type="docling")
        outputs = {root / f"struct/docling/{ident}.jsonl": jsonl(rows),
                   root / f"struct/documents/docling-{ident}.jsonl": jsonl(chunks)}
        for target, content in outputs.items():
            if target.exists() and target.read_bytes() != content:
                raise FileExistsError(f"기존 변환 결과를 보존합니다: {target}")
        for target, original in assets.items():
            if target.exists() and target.read_bytes() != original.read_bytes():
                raise FileExistsError(f"기존 자산을 보존합니다: {target}")
        for target, original in assets.items():
            preserve_write(target, original.read_bytes())
        for target, content in outputs.items():
            preserve_write(target, content)
        report["documents"].append({"document": info["document"], "pages": info["pages"],
                                    "chunks": len(chunks), "assets": len(assets), "machines": entry["machine_code"],
                                    "repeated_source_ids": repeated_ids})
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode()
    preserve_write(root / f"struct/reports/docling-{hashlib.sha256(payload).hexdigest()[:12]}.json", payload)
    return report
