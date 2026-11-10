"""Export existing embeddings once, for bounded machine-scoped reads in the API."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
for folder in (ROOT, ROOT / "backend"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

from app.core.machine_search import source_revision


def export_collection(collection, chroma_path, destination):
    import numpy as np

    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = collection.count()
    revision = source_revision(chroma_path, collection.name)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".sqlite3", delete=False) as f:
        temporary = Path(f.name)
    try:
        with closing(sqlite3.connect(temporary)) as conn:
            conn.executescript("""
                PRAGMA journal_mode=OFF;
                PRAGMA cache_size=-8192;
                CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE chunks (id TEXT UNIQUE NOT NULL, document TEXT NOT NULL,
                                     metadata TEXT NOT NULL, vector BLOB NOT NULL);
                CREATE TABLE machine_chunks (machine TEXT NOT NULL, chunk INTEGER NOT NULL,
                                             PRIMARY KEY(machine, chunk)) WITHOUT ROWID;
                CREATE TABLE documents (machine TEXT, source TEXT, kind TEXT,
                                        PRIMARY KEY(machine, source, kind)) WITHOUT ROWID;
            """)
            for offset in range(0, count, 256):
                batch = collection.get(limit=256, offset=offset, include=["documents", "metadatas", "embeddings"])
                for ident, text, meta, raw in zip(batch["ids"], batch["documents"], batch["metadatas"], batch["embeddings"]):
                    meta = meta or {}
                    codes = meta.get("machine_code") or []
                    codes = [codes] if isinstance(codes, str) else codes
                    if not codes or not text or not text.removeprefix("passage: ").strip():
                        continue
                    vector = np.asarray(raw, dtype="<f4")
                    norm = np.linalg.norm(vector)
                    if not norm or not np.isfinite(vector).all():
                        raise ValueError(f"Invalid embedding: {ident}")
                    vector = vector / norm
                    row = conn.execute("INSERT INTO chunks VALUES (?, ?, ?, ?)",
                                       (ident, text, json.dumps(meta, ensure_ascii=False), vector.tobytes())).lastrowid
                    for code in set(codes):
                        conn.execute("INSERT INTO machine_chunks VALUES (?, ?)", (code, row))
                        if meta.get("source_doc_name"):
                            conn.execute("INSERT OR IGNORE INTO documents VALUES (?, ?, ?)",
                                         (code, meta["source_doc_name"], meta.get("container_type", "")))
                conn.commit()
                if offset % 10240 == 0:
                    print(f"{min(offset + 256, count)}/{count}", flush=True)
            if source_revision(chroma_path, collection.name) != revision or collection.count() != count:
                raise RuntimeError("Source changed during export; retry with the builder stopped.")
            conn.executemany("INSERT INTO info VALUES (?, ?)", [
                ("version", "1"), ("collection", collection.name),
                ("source_revision", json.dumps(revision)), ("source_count", str(count)),
            ])
            conn.commit()
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Saved {destination}", flush=True)


def main():
    import argparse
    import chromadb
    from app.factories.config import get_factory_config
    from app.core.machine_search import index_path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--factory", required=True)
    args = parser.parse_args()
    config = get_factory_config("vllm_config", args.factory)
    client = chromadb.PersistentClient(path=config.vector_db.get_search_path("chroma"))
    collection = client.get_collection(config.vector_db.collection_name or config.id, embedding_function=None)
    export_collection(collection, config.vector_db.get_search_path("chroma"), index_path(config))


if __name__ == "__main__":
    main()
