"""Combine independently named manifests without rewriting received files."""
import json
from pathlib import Path

from pipeline.ingestion.prepared_documents import document_key


def load_manifests(source: Path, *, required: bool = False) -> dict:
    documents, origins = {}, {}
    for path in sorted((source / "_reports").glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict) or "documents" not in payload:
            continue
        if not isinstance(payload["documents"], list):
            raise ValueError(f"잘못된 manifest documents: {path}")
        for item in payload["documents"]:
            key = document_key(item["document"])
            folder = item["folder"]
            if Path(folder).name != folder or folder in {".", ".."}:
                raise ValueError(f"잘못된 문서 폴더: {path}: {folder}")
            if key in documents:
                previous = documents[key]
                for field in ("folder", "source_pdf_sha256", "pages", "original_pdf_pages", "result_pages"):
                    if previous.get(field) is not None and item.get(field) is not None and previous[field] != item[field]:
                        raise ValueError(f"manifest 충돌 ({field}): {item['document']} — {origins[key]} / {path}")
                for field, value in item.items():
                    previous.setdefault(field, value)
            else:
                documents[key] = dict(item)
                origins[key] = path
    if required and not documents:
        raise FileNotFoundError(f"문서 목록이 있는 manifest JSON이 필요합니다: {source / '_reports'}")
    return documents
