import re
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request

documentRouter = APIRouter(prefix="/api/documents", tags=["documents"])

DEFAULT_ASSET_ROOT = Path(__file__).resolve().parents[3] / "pipeline" / "data"


def _normalize_doc_name(value: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", value.lower())


def _first_page(page_range: str | None) -> int | None:
    if not page_range:
        return None

    match = re.search(r"\d+", page_range)
    if not match:
        return None

    return int(match.group(0))


def _asset_url(pdf_path: Path, asset_root: Path, page: int | None) -> str:
    relative_path = pdf_path.relative_to(asset_root)
    encoded_path = "/".join(quote(part) for part in relative_path.parts)
    url = f"/assets/{encoded_path}"
    return f"{url}#page={page}" if page is not None else url


def resolve_pdf_document(
    source_doc_name: str,
    page_range: str | None = None,
    asset_root: Path = DEFAULT_ASSET_ROOT,
) -> dict:
    normalized_source = _normalize_doc_name(source_doc_name)
    if not normalized_source:
        raise HTTPException(status_code=400, detail="source_doc_name is required.")

    pdf_paths = sorted(
        path
        for path in asset_root.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    )

    exact_matches = [
        path for path in pdf_paths if _normalize_doc_name(path.stem) == normalized_source
    ]
    contains_matches = [
        path
        for path in pdf_paths
        if _normalize_doc_name(path.stem) in normalized_source
        or normalized_source in _normalize_doc_name(path.stem)
    ]

    matched_path = (exact_matches or contains_matches or [None])[0]
    if matched_path is None:
        raise HTTPException(status_code=404, detail="PDF document not found.")

    page = _first_page(page_range)
    return {
        "document_name": matched_path.name,
        "asset_url": _asset_url(matched_path, asset_root, page),
        "page": page,
    }


@documentRouter.get("/resolve")
def resolve_document(
    request: Request,
    source_doc_name: str,
    page_range: str | None = None,
):
    asset_root = Path(getattr(request.app.state, "asset_root", DEFAULT_ASSET_ROOT))
    return resolve_pdf_document(
        source_doc_name=source_doc_name,
        page_range=page_range,
        asset_root=asset_root,
    )
