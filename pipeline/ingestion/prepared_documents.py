"""Factory layout and the boundary between external OCR and indexing.

Converters write one JSONL per document under struct/documents, using the index-ready chunk shape
(`id`, `page_content`, `metadata`) and copy referenced assets under asset.
"""
import json
from pathlib import Path
import unicodedata


INPUT_FOLDERS = ("manuals", "controllers", "electricals", "ladders",
                 "repairHistory", "knowledge", "extracted/paddleocr", "extracted/docling")
OUTPUT_FOLDERS = ("struct", "asset", "bm25", "chroma", "faiss", "electrical", "kg", "multimodal")


def initialize_layout(root: Path) -> None:
    for name in INPUT_FOLDERS:
        (root / "inputs" / name).mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_FOLDERS:
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / "struct" / "documents").mkdir(parents=True, exist_ok=True)


def document_key(name: str) -> str:
    name = unicodedata.normalize("NFC", name.replace("\\", "/").rsplit("/", 1)[-1]).strip()
    if Path(name).suffix.lower() in {".pdf", ".lst", ".lad"}:
        name = name[: -len(Path(name).suffix)]
    return name.casefold()


def document_catalog(machines: dict) -> dict:
    catalog = {}
    for code, info in machines.items():
        groups = info.get("document") or {}
        if not isinstance(groups, dict):
            raise ValueError(f"{code}: 문서 종류별 machine_info가 필요합니다.")
        for kind in ("manual", "controller", "electrical", "ladder"):
            for name in groups.get(kind, []):
                key = document_key(name)
                entry = catalog.setdefault(key, {"document_type": kind, "machine_code": []})
                if entry["document_type"] != kind:
                    raise ValueError(f"문서 종류가 충돌합니다: {name}")
                if code not in entry["machine_code"]:
                    entry["machine_code"].append(code)
    return catalog


def prepare_ocr(root: Path, machines: dict) -> None:
    from pipeline.ingestion.paddleocr_import import prepare_paddleocr
    from pipeline.ingestion.docling_import import docling_documents, prepare_docling

    documents = docling_documents(root)
    reports = {}
    if documents:
        reports["Docling"] = prepare_docling(root, machines, documents)
    paddle = root / "inputs/extracted/paddleocr"
    if paddle.exists() and any(p.is_dir() and p.name != "_reports" for p in paddle.iterdir()):
        reports["PaddleOCR"] = prepare_paddleocr(root, machines, docling_documents=documents)
    if not reports:
        raise FileNotFoundError("inputs/extracted에 추출 결과가 없습니다.")
    for name, report in reports.items():
        print(f"{name} 변환: {len(report['documents'])}개 문서, "
              f"{sum(d['pages'] for d in report['documents'])}쪽, "
              f"{sum(d['chunks'] for d in report['documents'])}개 청크; "
              f"보류 {len(report['skipped'])}개 문서", flush=True)


def prepare_ladders(root: Path, machines: dict, factory_id: str) -> None:
    """Reuse the existing LST parser; LAD is retained as an original, not decoded."""
    from pipeline.ingestion.chunk_refiner import ChunkRefiner
    from pipeline.parsers.mnemonic_ladder import build_mnemonic_files

    catalog = document_catalog(machines)
    sources = sorted(p for p in (root / "inputs" / "ladders").rglob("*")
                     if p.is_file() and p.suffix.lower() == ".lst")
    if not sources:
        raise FileNotFoundError("inputs/ladders에 LST 파일이 없습니다. LAD는 보관용입니다.")
    import hashlib
    targets = []
    for source in sources:
        key = document_key(source.name)
        if key not in catalog or catalog[key]["document_type"] != "ladder":
            raise ValueError(f"machine_info의 ladder에 연결되지 않은 문서: {source.name}")
        ident = hashlib.sha256(key.encode()).hexdigest()[:20]
        target = root / "struct" / "documents" / f"ladder-{ident}.jsonl"
        raw_dir = root / "struct" / "ladders" / ident
        if target.exists() or raw_dir.exists() or any(t[1] == target for t in targets):
            raise FileExistsError(f"기존 또는 중복 래더 결과를 보존합니다: {target}")
        targets.append((source, target, raw_dir))
    for source, target, raw_dir in targets:
        raw = build_mnemonic_files(source, raw_dir)
        chunks = ChunkRefiner().ladder_convert(raw, factory_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x", encoding="utf-8") as stream:
            for chunk in chunks:
                chunk["metadata"].update(catalog[document_key(source.name)])
                stream.write(json.dumps(chunk, ensure_ascii=False) + "\n")


def load_prepared_chunks(root: Path, machines: dict, factory_id: str) -> list[dict]:
    # Prefer only successfully prepared Docling documents, not merely imported inputs.
    preferred = set()
    for path in (root / "struct/documents").glob("docling-*.jsonl"):
        with path.open(encoding="utf-8-sig") as stream:
            for line in stream:
                if line.strip():
                    preferred.add(document_key(json.loads(line)["metadata"]["source_doc_name"]))
                    break
    catalog = document_catalog(machines)
    chunks, ids, unknown = [], set(), set()
    for path in sorted((root / "struct" / "documents").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            meta = dict(row["metadata"])
            source = meta["source_doc_name"]
            if meta.get("source_type") == "paddleocr" and document_key(source) in preferred:
                continue
            entry = catalog.get(document_key(source))
            if entry is None:
                unknown.add(source)
                continue
            if entry["document_type"] == "electrical":
                continue
            if not isinstance(row["id"], str) or not row["id"] or not isinstance(row["page_content"], str):
                raise ValueError(f"잘못된 표준 청크: {path}")
            if row["id"] in ids:
                raise ValueError(f"중복 청크 ID: {row['id']}")
            ids.add(row["id"])
            meta.update(entry)
            meta["chunk_id"] = row["id"]
            meta["site_id"] = factory_id
            chunks.append({"id": row["id"], "page_content": row["page_content"], "metadata": meta})
    if unknown:
        raise ValueError("machine_info에 연결되지 않은 문서: " + ", ".join(sorted(unknown)))
    if not chunks:
        raise ValueError("공용 인덱스에 넣을 표준 청크가 없습니다: struct/documents/*.jsonl")
    return chunks


def require_empty_indexes(root: Path, names=("chroma", "bm25", "faiss")) -> None:
    for name in names:
        path = root / name
        if path.exists() and (not path.is_dir() or any(path.iterdir())):
            raise FileExistsError(f"기존 인덱스를 보존합니다: {path}. 비어 있는 --output-root를 지정하세요.")
