"""Read-only retrieval for GraphIndexing v2 artifacts, independent of indexing LLM."""
from __future__ import annotations

import ast
import hashlib
import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from filelock import FileLock
from scipy import sparse

from .graph import ppr, unit


def artifact(index: Path, relative: str) -> Path:
    path = (index / relative.replace("\\", "/")).resolve()
    if not path.is_relative_to(index.resolve()):
        raise ValueError("Index artifact escapes its directory")
    return path


def vector_cache(source: Path, dimensions: int, cache: Path) -> np.ndarray:
    """Convert parquet once; serve float32 vectors through a memory mapped file."""
    stat = source.stat()
    key = hashlib.sha256(f"{source.resolve()}:{stat.st_size}:{stat.st_mtime_ns}:{dimensions}".encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{key}.npy"
    rows = pq.ParquetFile(source).metadata.num_rows
    with FileLock(str(target) + ".lock"):
        if not target.exists():
            temporary = target.with_suffix(".partial.npy")
            values = np.lib.format.open_memmap(temporary, mode="w+", dtype=np.float32,
                                               shape=(rows, dimensions))
            pos = 0
            try:
                for batch in pq.ParquetFile(source).iter_batches(batch_size=256, columns=["embedding"]):
                    column = batch.column(0)
                    offsets = column.offsets.to_numpy()
                    if column.null_count or column.values.null_count or not np.all(np.diff(offsets) == dimensions):
                        raise ValueError(f"Invalid embedding dimensions or null vector: {source}")
                    flat = column.values.slice(int(offsets[0]), int(offsets[-1] - offsets[0]))
                    arr = flat.to_numpy(zero_copy_only=False).reshape(len(column), dimensions)
                    if not np.isfinite(arr).all() or not np.allclose(np.linalg.norm(arr, axis=1), 1, atol=1e-4):
                        raise ValueError(f"Invalid or unnormalised vectors: {source}")
                    values[pos:pos + len(arr)] = arr
                    pos += len(arr)
                if pos != rows:
                    raise ValueError("Incomplete vector cache")
                values.flush()
            finally:
                values._mmap.close()  # Windows cannot rename an open mapped file.
                del values
            temporary.replace(target)
    result = np.load(target, mmap_mode="r")
    if result.shape != (rows, dimensions) or result.dtype != np.float32:
        raise ValueError(f"Invalid vector cache: {target}")
    return result


def top_positions(scores, count):
    count = min(count, len(scores))
    if count == 0:
        return np.empty(0, dtype=np.int64)
    candidates = np.argpartition(-scores, count - 1)[:count]
    return candidates[np.lexsort((candidates, -scores[candidates]))]


def prune_neighbors(matrix, count):
    """Bound table expansion at query time, preserving the source graph files."""
    matrix = matrix.tocsr()
    rows, cols, weights = [], [], []
    for row in range(matrix.shape[0]):
        lo, hi = matrix.indptr[row:row + 2]
        keep = top_positions(matrix.data[lo:hi], count) + lo
        rows.extend([row] * len(keep))
        cols.extend(matrix.indices[keep])
        weights.extend(matrix.data[keep])
    return sparse.csr_matrix((np.asarray(weights, dtype=np.float32), (rows, cols)), shape=matrix.shape)


class GraphIndexSearch:
    def __init__(self, index_dir, cache_dir, *, table_neighbors=8, damping=0.5):
        self.index_dir = Path(index_dir).resolve()
        self.manifest = json.loads((self.index_dir / "manifest.json").read_text(encoding="utf-8"))
        m = self.manifest
        if m.get("version") != 2 or not m.get("embedding_base_url"):
            raise ValueError("GraphIndexing v2 manifest with embedding endpoint is required")
        self.dimensions = int(m["embedding_dimensions"])
        self.damping = damping
        model = artifact(self.index_dir, m["hipporag_model_dir"])
        self.frames, self.vectors = {}, {}
        for namespace in ("chunk", "entity", "fact"):
            path = model / f"{namespace}_embeddings/vdb_{namespace}.parquet"
            self.frames[namespace] = pd.read_parquet(path, columns=["hash_id", "content"])
            self.vectors[namespace] = vector_cache(path, self.dimensions, Path(cache_dir))
        self.corpus = json.loads(artifact(self.index_dir, m["text_corpus"]).read_text(encoding="utf-8"))
        self.tables = [json.loads(line) for line in artifact(self.index_dir, m["tables"]).read_text(encoding="utf-8").splitlines() if line.strip()]
        g = artifact(self.index_dir, m["graph"])
        self.entity_idx = np.load(g / "entity_node_indices.npy")
        self.passage_idx = np.load(g / "passage_node_indices.npy")
        self.table_emb = np.load(g / "table_schema_embeddings.npy", mmap_mode="r")
        self.table_ids = np.load(g / "table_idxs.npy")
        e, p, t = len(self.entity_idx), len(self.passage_idx), len(self.tables)
        if (e, p, t) != (m["entities"], m["passages"], m["table_count"]):
            raise ValueError("Manifest node counts differ")
        if len(self.frames["entity"]) != e or len(self.frames["chunk"]) != p or len(self.corpus) != p:
            raise ValueError("Vector row mappings differ")
        if self.table_emb.shape != (t, self.dimensions) or self.table_ids.tolist() != [r["table_idx"] for r in self.tables]:
            raise ValueError("Table row mappings differ")
        if not np.array_equal(np.sort(np.concatenate([self.entity_idx, self.passage_idx])), np.arange(e + p)):
            raise ValueError("Text node mappings are not a partition")
        self.table_offset, self.n_nodes = e + p, e + p + t
        self.entity_lookup = {text: int(node) for text, node in zip(self.frames["entity"]["content"], self.entity_idx)}
        self.passage_rows = []
        for content in self.frames["chunk"]["content"]:
            pos, body = content.split(":", 1)
            row = self.corpus[int(pos)]
            if body != row["text"]:
                raise ValueError("Stored passage does not match source corpus")
            self.passage_rows.append(row)
        base = sparse.load_npz(g / "hipporag_adjacency.npz").tocsr()
        tt = sparse.load_npz(g / "table_table.npz")
        pt = sparse.load_npz(g / "passage_table.npz").tocoo()
        if base.shape != (self.n_nodes, self.n_nodes) or tt.shape != (t, t) or pt.shape != (p, t):
            raise ValueError("Graph dimensions differ")
        tt = prune_neighbors(tt, table_neighbors).tocoo()
        left, right = self.passage_idx[pt.row], pt.col + self.table_offset
        rows = np.concatenate([tt.row + self.table_offset, left, right])
        cols = np.concatenate([tt.col + self.table_offset, right, left])
        weights = np.concatenate([tt.data, pt.data, pt.data])
        adj = base + sparse.csr_matrix((weights, (rows, cols)), shape=base.shape)
        sums = np.asarray(adj.sum(axis=1)).ravel()
        inverse = np.divide(1.0, sums, out=np.zeros_like(sums), where=sums > 0)
        self.transition = (sparse.diags(inverse) @ adj).tocsr()
        self.dangling = sums == 0

    def retrieve(self, vector, top_k=8, *, trace=None):
        if top_k < 1:
            raise ValueError("top_k must be positive")
        vector = unit(np.asarray(vector, dtype=np.float32))
        if vector.shape != (self.dimensions,):
            raise ValueError("Query embedding dimension differs from index")
        sims = {key: np.maximum(values @ vector, 0) for key, values in self.vectors.items()}
        table_sim = np.maximum(self.table_emb @ vector, 0)
        seed = np.zeros(self.n_nodes, dtype=np.float32)

        def add_seed(nodes, scores, weight, count=32):
            chosen = top_positions(scores, count)
            total = float(scores[chosen].sum())
            if total > 0:
                np.add.at(seed, np.asarray(nodes)[chosen], weight * scores[chosen] / total)

        add_seed(self.passage_idx, sims["chunk"], 0.35)
        add_seed(np.arange(len(self.tables)) + self.table_offset, table_sim, 0.35)
        add_seed(self.entity_idx, sims["entity"], 0.10, 16)
        fact_nodes, fact_weights = [], []
        for pos in top_positions(sims["fact"], 24):
            if sims["fact"][pos] <= 0:
                continue
            triple = ast.literal_eval(self.frames["fact"].iloc[int(pos)]["content"])
            if not isinstance(triple, (tuple, list)) or len(triple) != 3:
                raise ValueError("Malformed stored fact")
            for entity in (triple[0], triple[2]):
                node = self.entity_lookup.get(str(entity))
                if node is not None:
                    fact_nodes.append(node)
                    fact_weights.append(float(sims["fact"][pos]))
        if fact_weights:
            np.add.at(seed, fact_nodes, 0.20 * np.asarray(fact_weights) / sum(fact_weights))
        if seed.sum() <= 0:
            raise ValueError("질문과 관련된 매뉴얼 근거를 찾지 못했습니다.")
        scores = ppr(self.transition, self.dangling, seed / seed.sum(), self.damping)
        if trace is not None:
            trace.update(seed=seed / seed.sum(), scores=scores.copy())
        direct = np.concatenate([sims["chunk"], table_sim])
        graph = np.concatenate([scores[self.passage_idx], scores[self.table_offset:]])
        # Fuse ranks rather than comparing cosine similarity to PageRank scores.
        fused = np.zeros(len(direct), dtype=np.float32)
        for values, weight in ((direct, 0.65), (graph, 0.35)):
            ranked = top_positions(values, min(256, len(values)))
            ranked = ranked[values[ranked] > 0]
            fused[ranked] += weight / (60 + np.arange(1, len(ranked) + 1))
        out = []
        for pos in top_positions(fused, min(top_k, len(fused))):
            if fused[pos] <= 0:
                continue
            if pos < len(self.passage_rows):
                row = self.passage_rows[int(pos)]
                item = {"type": "passage", "id": str(self.frames["chunk"].iloc[int(pos)]["hash_id"]),
                        "content": row["text"], "source": {"source_doc_name": row["source_doc"],
                        "page_range": row["pages"]["range"], "section_title": row.get("title", "")}}
            else:
                table = self.tables[int(pos) - len(self.passage_rows)]
                meta = dict(table["metadata"])
                pages = meta.get("page_range", meta.get("page_no", ""))
                if isinstance(pages, dict):
                    pages = pages.get("range", "")
                merge_pages = meta.get("merge", {}).get("page_range")
                if not pages or (not meta.get("page_range") and meta.get("merge", {}).get("is_merged")):
                    source_pages = meta.get("merge", {}).get("source_pages", [])
                    if source_pages:
                        pages = f"{min(source_pages)}-{max(source_pages)}"
                if merge_pages:
                    pages = merge_pages.get("range", pages) if isinstance(merge_pages, dict) else merge_pages
                meta.update(source_doc_name=meta.get("document", meta.get("document_file", "")),
                            page_range=str(pages), section_title=meta.get("struct_section", ""))
                item = {"type": "table", "id": table["table_idx"], "caption": table["caption"],
                        "table": table["table"], "source": meta}
            item.update(score=float(fused[pos]), direct_score=float(direct[pos]), graph_score=float(graph[pos]))
            out.append(item)
        return out


_SEARCHES = OrderedDict()


def get_search(index_dir, cache_dir):
    path = Path(index_dir).resolve()
    stat = (path / "manifest.json").stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, str(Path(cache_dir).resolve()))
    if key not in _SEARCHES:
        _SEARCHES[key] = GraphIndexSearch(path, cache_dir)
        while len(_SEARCHES) > 2:
            _SEARCHES.popitem(last=False)
    _SEARCHES.move_to_end(key)
    return _SEARCHES[key]
