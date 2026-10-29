"""Build controller integration in temporary staging, not a separate runtime store.

Run with the backend environment: python -m pipeline.integrate_controller FACTORY ARCHIVE
After verification, install chroma/bm25/faiss/chunks.jsonl in the factory root.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import pickle
import shutil
import sqlite3
import zipfile

import chromadb
import faiss
import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi

from backend.app.core.bm25_tokenizer import tokenize_for_bm25, TOKENIZER_VERSION

ROOT = Path(__file__).resolve().parents[1]


def normalize_chunk(chunk, factory, machines):
    row = {**chunk, "metadata": dict(chunk["metadata"])}
    meta = row["metadata"]
    original = meta["original_doc_name"]
    expected = sorted(code for code, info in machines.items()
                      if original in info["document"].get("controller", []))
    if not expected or sorted(meta["machine_code"]) != expected:
        raise ValueError(f"Controller machine mapping mismatch: {original}")
    meta["source_doc_name"] = Path(original).stem
    meta["document_kinds"] = ["controller"]
    for key in ("asset_path", "source_pdf"):
        if meta.get(key):
            relative = Path(meta[key])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Invalid archive path: {relative}")
            relative = Path("inputs") / relative.name if key == "source_pdf" else relative
            meta[key] = f"{factory}/controller/{relative.as_posix()}"
    return row


def integrate(factory, archive):
    site = ROOT / "pipeline/data" / factory
    stage = site / ".controller_import_staging"
    stage.mkdir(exist_ok=False)
    settings = json.loads((site / "build_info/search_settings.json").read_text(encoding="utf-8"))
    machines = json.loads((ROOT / f"backend/app/factories/machine_info_{factory}.json").read_text(encoding="utf-8"))
    old = site
    with (old / "bm25/bm25_bundle.pkl").open("rb") as stream:
        bundle = pickle.load(stream)
    original_ids = list(bundle["ids"])
    rows = pd.read_parquet(old / "faiss/chunks.parquet").to_dict("records")
    assert [r["id"] for r in rows] == original_ids
    index = faiss.read_index(str(old / "faiss/faiss.index"))
    assert index.ntotal == len(rows) and index.d == 4096
    # Preserve the complete existing index; never mutate the live database.
    shutil.copytree(old / "chroma", stage / "chroma",
                    ignore=shutil.ignore_patterns("chroma.sqlite3*"))
    with sqlite3.connect((old / "chroma/chroma.sqlite3").resolve().as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(stage / "chroma/chroma.sqlite3") as target:
            source.backup(target)
    client = chromadb.PersistentClient(path=str(stage / "chroma"))
    collection = client.get_collection(settings["collection"], embedding_function=None)
    assert collection.count() == len(original_ids)
    assert collection.metadata["hnsw:space"] == "cosine"
    with zipfile.ZipFile(archive) as z:
        incoming_settings = json.loads(z.read(f"{factory}/search_settings.json"))
        assert incoming_settings["embedding_model"] == settings["embedding_model"]
        with z.open(f"{factory}/chunks.jsonl") as stream:
            incoming = [normalize_chunk(json.loads(line), factory, machines) for line in stream]
        assert not set(original_ids) & {r["id"] for r in incoming}
        for info in z.infolist():
            prefix = f"{factory}/"
            if not info.filename.startswith((prefix + "assets/", prefix + "original_pdfs/")) or info.is_dir():
                continue
            relative = Path(info.filename[len(prefix):])
            if relative.parts[0] == "original_pdfs":
                relative = Path("inputs") / relative.name
            target = (site / "controller" / relative).resolve()
            if not target.is_relative_to((site / "controller").resolve()):
                raise ValueError(info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
        vector_path = stage / "controller.faiss"
        with z.open(f"{factory}/store/faiss/faiss.index") as src, vector_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)
    incoming_index = faiss.read_index(str(vector_path))
    assert incoming_index.ntotal == len(incoming) and incoming_index.d == index.d
    for start in range(0, len(incoming), 500):
        batch = incoming[start:start + 500]
        vectors = incoming_index.reconstruct_n(start, len(batch))
        assert np.isfinite(vectors).all()
        # Archive FAISS vectors are normalized copies of the Chroma vectors.
        # Normalization preserves cosine distance in the existing Chroma collection.
        collection.add(ids=[r["id"] for r in batch], embeddings=vectors,
                       documents=["passage: " + r["page_content"] for r in batch],
                       metadatas=[r["metadata"] for r in batch])
        index.add(vectors)
        if start % 5000 == 0:
            print(f"{factory}: {start + len(batch)}/{len(incoming)} controller vectors", flush=True)
    del incoming_index
    rows.extend(incoming)
    bundle["ids"].extend(r["id"] for r in incoming)
    bundle["documents"].extend("passage: " + r["page_content"] for r in incoming)
    bundle["metadatas"].extend(r["metadata"] for r in incoming)
    bundle["bm25"] = BM25Okapi([tokenize_for_bm25(t.removeprefix("passage: ")) for t in bundle["documents"]])
    bundle["meta"].update(chunk_count=len(rows), tokenizer=TOKENIZER_VERSION)
    (stage / "bm25").mkdir()
    with (stage / "bm25/bm25_bundle.pkl").open("wb") as stream:
        pickle.dump(bundle, stream)
    (stage / "bm25/bm25_bundle.meta.json").write_text(json.dumps(bundle["meta"], indent=2), encoding="utf-8")
    (stage / "faiss").mkdir()
    faiss.write_index(index, str(stage / "faiss/faiss.index"))
    # PaddleOCR stores page numbers as strings; Docling archives use integers.
    # Use one Parquet field type without changing persisted Chroma/BM25 metadata.
    parquet_rows = [{**r, "metadata": {**r["metadata"],
                    "pdf_page": str(r["metadata"].get("pdf_page", ""))}} for r in rows]
    pd.DataFrame(parquet_rows).to_parquet(stage / "faiss/chunks.parquet", index=False)
    with (stage / "chunks.jsonl").open("w", encoding="utf-8") as stream:
        for ident, document, meta in zip(bundle["ids"], bundle["documents"], bundle["metadatas"]):
            stream.write(json.dumps(dict(id=ident, page_content=document.removeprefix("passage: "), metadata=meta), ensure_ascii=False) + "\n")
    assert collection.count() == index.ntotal == len(bundle["ids"])
    for start in range(0, len(original_ids), 500):
        found = collection.get(ids=original_ids[start:start + 500], include=["documents", "metadatas"])
        positions = {ident: start + n for n, ident in enumerate(original_ids[start:start + 500])}
        for ident, document, meta in zip(found["ids"], found["documents"], found["metadatas"]):
            pos = positions[ident]
            assert document == bundle["documents"][pos] and meta == bundle["metadatas"][pos]
        assert len(found["ids"]) == len(positions)
    for row in incoming:
        for key in ("asset_path", "source_pdf"):
            if row["metadata"].get(key):
                assert (ROOT / "pipeline/data" / row["metadata"][key]).is_file()
    report = dict(factory=factory, original_count=len(original_ids), controller_count=len(incoming),
                  total_count=collection.count(), original_records_unchanged=True,
                  controller_per_machine=dict(Counter(code for r in incoming for code in r["metadata"]["machine_code"])),
                  attachment_paths_verified=True, staging_directory=stage.name)
    (stage / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    vector_path.unlink()
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("factory", choices=["yulkok", "poongsan"])
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    integrate(args.factory, args.archive)
