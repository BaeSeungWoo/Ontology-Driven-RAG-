"""Graph construction and personalized PageRank.

Node layout of every graph: [entities + passages] (HippoRAG order) followed by tables.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import sparse


def minmax(x) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    lo, hi = float(x.min()), float(x.max())
    return (x - lo) / (hi - lo) if hi > lo else np.zeros_like(x)


def unit(x) -> np.ndarray:
    """L2-normalise a vector or the rows of a matrix."""
    x = np.asarray(x, dtype=np.float32)
    norm = np.linalg.norm(x, axis=-1, keepdims=True)
    if not np.isfinite(x).all() or np.any(norm <= 0):
        raise ValueError("invalid embedding")
    return x / norm


def threshold_similarity(left: np.ndarray, right: np.ndarray, threshold: float,
                         symmetric: bool, batch: int = 128) -> sparse.csr_matrix:
    """Sparse cosine matrix keeping entries >= threshold (and no self-loops if symmetric)."""
    rows, cols, vals = [], [], []
    for start in range(0, len(left), batch):
        scores = left[start:start + batch] @ right.T
        r, c = np.where(scores >= threshold)
        if symmetric:
            keep = r + start != c
            r, c = r[keep], c[keep]
        rows.append((r + start).astype(np.int32))
        cols.append(c.astype(np.int32))
        vals.append(scores[r, c].astype(np.float32))
    if not rows:
        return sparse.csr_matrix((len(left), len(right)), dtype=np.float32)
    m = sparse.coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(len(left), len(right)), dtype=np.float32).tocsr()
    m.sum_duplicates()
    return m


def transition_matrix(graph_dir: Path, integrated: bool) -> tuple[sparse.csr_matrix, np.ndarray]:
    """Row-stochastic transition over HippoRAG + table-table edges (+ passage-table if integrated).

    Returns the matrix and a mask of dangling (zero out-degree) nodes.
    """
    base = sparse.load_npz(graph_dir / "hipporag_adjacency.npz").tocsr()
    offset = base.shape[0] - len(np.load(graph_dir / "table_idxs.npy"))
    tt = sparse.load_npz(graph_dir / "table_table.npz").tocoo()
    adj = base + sparse.coo_matrix((tt.data, (tt.row + offset, tt.col + offset)),
                                   shape=base.shape, dtype=np.float32).tocsr()
    if integrated:
        pt = sparse.load_npz(graph_dir / "passage_table.npz").tocoo()
        left = np.load(graph_dir / "passage_node_indices.npy")[pt.row]
        right = pt.col + offset
        adj += sparse.coo_matrix((np.concatenate([pt.data, pt.data]),
                                  (np.concatenate([left, right]), np.concatenate([right, left]))),
                                 shape=base.shape, dtype=np.float32).tocsr()
    adj.sum_duplicates()
    out_deg = np.asarray(adj.sum(axis=1)).ravel()
    inv = np.divide(1.0, out_deg, out=np.zeros_like(out_deg), where=out_deg > 0)
    return (sparse.diags(inv) @ adj).tocsr(), out_deg == 0


def ppr(transition: sparse.csr_matrix, dangling: np.ndarray, seed: np.ndarray,
        damping: float, iters: int = 50, tol: float = 1e-6) -> np.ndarray:
    """Personalized PageRank; each step restarts to `seed` with probability 1 - damping."""
    scores = seed.copy()
    for _ in range(iters):
        nxt = transition.T @ scores
        if np.any(dangling):
            nxt += seed * scores[dangling].sum()
        nxt = (1.0 - damping) * seed + damping * nxt
        if float(np.abs(nxt - scores).sum()) < tol:
            return nxt
        scores = nxt
    return scores
