"""Read only the selected machine's search rows; never open a factory HNSW index."""
from contextlib import closing
import heapq
import json
from pathlib import Path
import sqlite3


def index_path(config):
    return Path(config.vector_db.get_search_path("bm25")) / "machine_search.sqlite3"


def source_revision(chroma_path, collection_name):
    # Logical revisions survive WAL checkpoints and read-only client restarts.
    with closing(connect(Path(chroma_path) / "chroma.sqlite3")) as conn:
        collection = conn.execute("SELECT id, dimension FROM collections WHERE name = ?",
                                  (collection_name,)).fetchone()
        if collection is None:
            raise ValueError("원본 검색 컬렉션이 없습니다.")
        sequences = conn.execute(
            "SELECT s.id, m.seq_id FROM segments s LEFT JOIN max_seq_id m ON m.segment_id = s.id "
            "WHERE s.collection = ? ORDER BY s.id", (collection[0],)).fetchall()
        return [collection, [(ident, seq.hex() if isinstance(seq, bytes) else seq) for ident, seq in sequences]]


def connect(path):
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA cache_size=-4096")
    conn.execute("PRAGMA mmap_size=0")
    return conn


class MachineSearch:
    def __init__(self, config):
        self.path = index_path(config)
        self.config = config

    def _validate(self, conn):
        meta = dict(conn.execute("SELECT key, value FROM info"))
        expected = self.config.vector_db.collection_name or self.config.id
        if meta.get("collection") != expected or meta.get("version") != "1":
            raise ValueError("장비 검색 DB가 현재 공장 설정과 일치하지 않습니다.")
        revision = json.dumps(source_revision(self.config.vector_db.get_search_path("chroma"), expected))
        if meta.get("source_revision") != revision:
            raise ValueError("원본 검색 DB가 변경되었습니다. 장비 검색 DB를 갱신해 주세요.")

    def records(self, machine_code):
        with closing(connect(self.path)) as conn:
            self._validate(conn)
            return tuple(conn.execute(
                "SELECT machine, source, kind FROM documents WHERE machine = ?", (machine_code,)))

    def _rows(self, machine_code, vectors=False):
        if not machine_code or machine_code == "ALL" or machine_code not in self.config.machines:
            raise ValueError("검색할 장비를 선택해 주세요.")
        with closing(connect(self.path)) as conn:
            self._validate(conn)
            from pipeline.ingestion.machine_resolver import machine_documents
            from pipeline.ingestion.prepared_documents import document_key
            linked = [document_key(name) for name in machine_documents(self.config.machines[machine_code])]
            sources = [source for (source,) in conn.execute(
                "SELECT DISTINCT source FROM documents WHERE machine = ?", (machine_code,))
                if any(key in document_key(source) or document_key(source) in key for key in linked)]
            if not sources:
                return
            columns = "c.id, c.document, c.metadata" + (", c.vector" if vectors else "")
            placeholders = ",".join("?" for _ in sources)
            cursor = conn.execute(
                f"SELECT {columns} FROM machine_chunks m JOIN chunks c ON c.rowid = m.chunk "
                "WHERE m.machine = ? AND json_extract(c.metadata, '$.source_doc_name') "
                f"IN ({placeholders}) ORDER BY m.chunk", (machine_code, *sources))
            while batch := cursor.fetchmany(64):
                yield batch

    def bm25(self, machine_code):
        from rank_bm25 import BM25Okapi
        from app.core.bm25_tokenizer import tokenize_for_bm25

        bundle = {"ids": [], "documents": [], "metadatas": []}
        tokens = []
        for batch in self._rows(machine_code):
            for ident, text, metadata in batch:
                bundle["ids"].append(ident)
                bundle["documents"].append(text)
                bundle["metadatas"].append(json.loads(metadata))
                tokens.append(tokenize_for_bm25(text.removeprefix("passage: ")))
        if not any(tokens):
            return None
        bundle["bm25"] = BM25Okapi(tokens)
        return bundle

    def get(self, machine_code, *, where=None):
        result = {"ids": [], "documents": [], "metadatas": []}
        for batch in self._rows(machine_code):
            for ident, text, metadata in batch:
                meta = json.loads(metadata)
                if _matches(meta, where):
                    result["ids"].append(ident)
                    result["documents"].append(text)
                    result["metadatas"].append(meta)
        return result

    def query(self, machine_code, embedding_fn, *, query_texts, n_results, where=None,
              where_document=None, include=None):
        import numpy as np

        if len(query_texts) != 1:
            raise ValueError("장비 검색은 한 번에 한 질문을 처리합니다.")
        vector = np.asarray(embedding_fn(query_texts)[0], dtype=np.float32)
        norm = np.linalg.norm(vector)
        if not norm or not np.isfinite(vector).all():
            raise ValueError("질문 임베딩이 올바르지 않습니다.")
        vector = vector / norm
        best = []
        for batch in self._rows(machine_code, vectors=True):
            rows = []
            for ident, text, metadata, blob in batch:
                meta = json.loads(metadata)
                if _matches(meta, where) and _matches_document(text, where_document):
                    rows.append((ident, text, meta, blob))
            if not rows:
                continue
            vectors = np.stack([np.frombuffer(row[3], dtype="<f4") for row in rows])
            scores = vectors @ vector
            for row, score in zip(rows, scores):
                candidate = (float(score), row[0], row[1], row[2])
                if len(best) < n_results:
                    heapq.heappush(best, candidate)
                elif candidate[:2] > best[0][:2]:
                    heapq.heapreplace(best, candidate)
        best.sort(key=lambda row: (-row[0], row[1]))
        return {"ids": [[r[1] for r in best]], "documents": [[r[2] for r in best]],
                "metadatas": [[r[3] for r in best]], "distances": [[1 - r[0] for r in best]]}


def _matches(meta, where):
    if not where:
        return True
    if "$and" in where:
        return all(_matches(meta, part) for part in where["$and"])
    for key, expected in where.items():
        actual = meta.get(key)
        if isinstance(expected, dict):
            if "$contains" in expected:
                values = [actual] if isinstance(actual, str) else (actual or [])
                if expected["$contains"] not in values:
                    return False
            elif "$ne" in expected:
                if actual == expected["$ne"]:
                    return False
            else:
                raise ValueError(f"Unsupported metadata filter: {expected}")
        elif actual != expected:
            return False
    return True


def _matches_document(text, where):
    if not where:
        return True
    if "$or" in where:
        return any(_matches_document(text, part) for part in where["$or"])
    if "$contains" in where:
        return where["$contains"] in text
    raise ValueError(f"Unsupported document filter: {where}")
