"""KG construction and retrieval helpers."""

from __future__ import annotations

import pickle
import re
from pathlib import Path

import networkx as nx
import numpy as np

TRIPLE_RE = re.compile(r"\(\s*([^,()]+?)\s*,\s*([^,()]+?)\s*,\s*([^()]+?)\s*\)")


def parse_triples(evidence_triple_str: str) -> list[tuple[str, str, str]]:
    """Parse '(s, p, o); (s, p, o)' into list of triples."""
    if not evidence_triple_str:
        return []
    out = []
    for m in TRIPLE_RE.finditer(evidence_triple_str):
        s, p, o = (m.group(i).strip().strip("'\"") for i in (1, 2, 3))
        if s and p and o:
            out.append((s, p, o))
    return out


def save_kg(g: nx.MultiDiGraph, entity_list: list[str], pkl_path: Path, ent_list_path: Path):
    with open(pkl_path, "wb") as f:
        pickle.dump(g, f)
    import orjson

    with open(ent_list_path, "wb") as f:
        f.write(orjson.dumps(entity_list))


def load_kg(pkl_path: Path, ent_list_path: Path) -> tuple[nx.MultiDiGraph, list[str]]:
    import orjson

    with open(pkl_path, "rb") as f:
        g = pickle.load(f)
    with open(ent_list_path, "rb") as f:
        entity_list = orjson.loads(f.read())
    return g, entity_list


def match_entities(
    query_emb: np.ndarray,
    entity_embs: np.ndarray,
    entity_list: list[str],
    top_k: int = 5,
    min_score: float = 0.5,
) -> list[tuple[str, float]]:
    """Cosine top-k entities for the query. Embeddings are L2-normalized."""
    if entity_embs.size == 0:
        return []
    sims = entity_embs @ query_emb.reshape(-1)
    order = np.argsort(-sims)[: top_k]
    out = []
    for idx in order:
        s = float(sims[idx])
        if s < min_score:
            continue
        out.append((entity_list[idx], s))
    return out


def expand_neighbors(
    g: nx.MultiDiGraph, seed_entities: list[str], radius: int = 1, max_triples: int = 30
) -> tuple[list[tuple[str, str, str]], set[str]]:
    """N-hop expansion (radius 1 or 2). Returns (triples_surface, sections)."""
    seen_edges: set = set()
    triples_surface: list[tuple[str, str, str]] = []
    sections: set[str] = set()
    undir = g.to_undirected(as_view=False)
    for ent in seed_entities:
        if not g.has_node(ent):
            continue
        ego_nodes = nx.ego_graph(undir, ent, radius=radius).nodes()
        for u, v, k, d in g.edges(ego_nodes, keys=True, data=True):
            edge_id = (u, v, k)
            if edge_id in seen_edges:
                continue
            seen_edges.add(edge_id)
            triples_surface.append(d.get("surface") or (u, d.get("predicate", ""), v))
            sections.update(d.get("sections") or set())
            if len(triples_surface) >= max_triples:
                break
        if len(triples_surface) >= max_triples:
            break
    return triples_surface, sections


def expand_smart(
    g: nx.MultiDiGraph,
    seed_entities: list[str],
    min_sections: int = 2,
    max_triples_1hop: int = 20,
    max_triples_2hop: int = 40,
) -> tuple[list[tuple[str, str, str]], set[str], int]:
    """Try 1-hop first; if too few sections were recovered, expand to 2-hop.

    Returns (triples, sections, hops_used). Complex Reasoning questions chain
    two triples (e.g. "section X.Y covers X.Y.Z which includes X.Y.Z.W") and
    1-hop misses them.
    """
    triples, sections = expand_neighbors(g, seed_entities, radius=1, max_triples=max_triples_1hop)
    if len(sections) >= min_sections:
        return triples, sections, 1
    # Expand to 2-hop, replacing the result (it is a superset).
    t2, s2 = expand_neighbors(g, seed_entities, radius=2, max_triples=max_triples_2hop)
    return t2, s2, 2


def build_kg_openie(
    chunk_records: list[dict],
    openie_results: list,
) -> tuple[nx.MultiDiGraph, list[str]]:
    """Build a HippoRAG-style heterogeneous KG from OpenIE output.

    Nodes:
      - entity nodes: ``kind='entity'``, key=lower-cased surface
      - passage nodes: ``kind='passage'``, key='passage::<chunk_id>'

    Edges:
      - entity → entity: predicate edge (from OpenIE triple), attr ``surface=(s,p,o)``,
        ``sections={section_title}``
      - entity → passage: ``predicate='appears_in'`` (both s and o → passage node)

    Args:
        chunk_records: list of dicts with chunk_id, section_title, doc_name, page_range.
        openie_results: list of ``OpenIEResult`` aligned with chunk_records.
    """
    g = nx.MultiDiGraph()
    chunk_by_id = {c["chunk_id"]: c for c in chunk_records}

    for r in openie_results:
        cid = r.chunk_id
        meta = chunk_by_id.get(cid) or {}
        section_title = meta.get("section_title") or ""
        doc_name = meta.get("doc_name") or ""
        page = meta.get("page_range")
        passage_key = f"passage::{cid}"
        if not g.has_node(passage_key):
            g.add_node(
                passage_key,
                kind="passage",
                chunk_id=cid,
                doc_name=doc_name,
                section_title=section_title,
                page_range=page,
            )
        for s, p, o in r.triples:
            sl, ol = s.lower().strip(), o.lower().strip()
            if not (sl and ol):
                continue
            if not g.has_node(sl):
                g.add_node(sl, kind="entity", surface=s)
            if not g.has_node(ol):
                g.add_node(ol, kind="entity", surface=o)
            g.add_edge(
                sl, ol,
                predicate=p,
                surface=(s, p, o),
                sections={section_title} if section_title else set(),
                chunk_ids={cid},
            )
            # link both endpoints to the passage node
            g.add_edge(sl, passage_key, predicate="appears_in")
            g.add_edge(ol, passage_key, predicate="appears_in")

    entity_list = sorted(n for n, d in g.nodes(data=True) if d.get("kind") == "entity")
    print(
        f"KG (OpenIE): {g.number_of_nodes()} nodes "
        f"({len(entity_list)} entities + "
        f"{sum(1 for _, d in g.nodes(data=True) if d.get('kind') == 'passage')} passages), "
        f"{g.number_of_edges()} edges"
    )
    return g, entity_list


def add_synonym_edges(
    g: nx.MultiDiGraph,
    entity_list: list[str],
    entity_embs: np.ndarray,
    threshold: float = 0.85,
    max_per_node: int = 5,
) -> int:
    """HippoRAG2 step ⑥: connect surface-similar entities with `synonym` edges
    so PPR mass flows between paraphrases.

    Only adds edges between kind='entity' nodes. Self-loops skipped.
    Returns number of edges added.
    """
    if entity_embs is None or len(entity_list) == 0:
        return 0
    sim = entity_embs @ entity_embs.T   # (N, N) cosine, embeddings already L2-normalized
    n = len(entity_list)
    np.fill_diagonal(sim, -1.0)
    added = 0
    for i in range(n):
        order = np.argsort(-sim[i])
        added_this = 0
        for j in order:
            if added_this >= max_per_node:
                break
            s = float(sim[i, j])
            if s < threshold:
                break
            u, v = entity_list[i], entity_list[j]
            if not (g.has_node(u) and g.has_node(v)):
                continue
            # avoid duplicating in the reverse direction (we still add both ways below)
            already = any(d.get("predicate") == "synonym" for _, _, d in g.edges([u], data=True) if _ == u)
            g.add_edge(u, v, predicate="synonym", surface=(u, "synonym", v), sections=set(), score=s)
            added += 1
            added_this += 1
    print(f"synonym edges added: {added} (threshold={threshold})")
    return added


def merge_kgs(g1: nx.MultiDiGraph, g2: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """Merge two KGs. Same-key nodes have their attributes combined; edges are
    appended (set-valued attrs unioned)."""
    out = nx.MultiDiGraph()
    for src in (g1, g2):
        for n, d in src.nodes(data=True):
            if out.has_node(n):
                # union of dict attrs
                for k, v in d.items():
                    if isinstance(v, set):
                        out.nodes[n].setdefault(k, set()).update(v)
                    elif k not in out.nodes[n]:
                        out.nodes[n][k] = v
            else:
                out.add_node(n, **{k: (set(v) if isinstance(v, set) else v) for k, v in d.items()})
        for u, v, d in src.edges(data=True):
            attrs = {k: (set(val) if isinstance(val, set) else val) for k, val in d.items()}
            out.add_edge(u, v, **attrs)
    return out


def normalize_section(t: str) -> str:
    """Normalize for prefix matching across slight formatting differences."""
    return re.sub(r"\s+", " ", t).strip().lower()


def expand_bfs(
    g: nx.MultiDiGraph,
    seeds: list[str],
    query_emb: np.ndarray,
    triple_embs: np.ndarray,
    edge_to_row: dict[tuple, int],
    max_triples: int = 20,
    min_edge_score: float = 0.30,
    max_depth: int = 4,
) -> tuple[list[tuple[str, str, str]], set[str], list[float]]:
    """Best-first BFS — at each step pick the highest-cosine (triple_text vs query) edge.

    Distance is not a hard cap; we just rank edges by relevance and stop once
    we've collected `max_triples` or the next-best edge is below `min_edge_score`.

    Returns (triples_surface, sections_union, scores).
    """
    import heapq

    # candidate edges: edge_key -> (score, surface, sections, distance)
    candidates: dict[tuple, tuple[float, tuple, set, int]] = {}
    visited_nodes: set[str] = set()
    triples_out: list[tuple[str, str, str]] = []
    sections_out: set[str] = set()
    scores_out: list[float] = []

    def _add_node_edges(node: str, distance: int):
        if not g.has_node(node):
            return
        for u, v, k, d in g.edges(node, keys=True, data=True):
            ek = (u, v, k)
            if ek in candidates:
                continue
            row = edge_to_row.get(ek)
            if row is None:
                continue
            cos = float(triple_embs[row] @ query_emb)
            surface = d.get("surface") or (u, d.get("predicate", ""), v)
            secs = d.get("sections") or set()
            candidates[ek] = (cos, surface, secs, distance)

    for s in seeds:
        if s not in visited_nodes and g.has_node(s):
            visited_nodes.add(s)
            _add_node_edges(s, distance=0)

    # heap-based best-first selection
    while candidates and len(triples_out) < max_triples:
        best_ek = max(candidates, key=lambda k: candidates[k][0])
        cos, surface, secs, dist = candidates.pop(best_ek)
        if cos < min_edge_score:
            break
        triples_out.append(surface)
        sections_out.update(secs)
        scores_out.append(cos)
        if dist >= max_depth:
            continue
        # expand: enqueue edges of the newly-touched endpoint(s)
        u, v, _ = best_ek
        for nb in (u, v):
            if nb not in visited_nodes:
                visited_nodes.add(nb)
                _add_node_edges(nb, distance=dist + 1)

    return triples_out, sections_out, scores_out


def sections_to_chunks(
    section_titles: set[str], chunks_df, max_chunks: int = 8
) -> list[dict]:
    """Look up chunks whose section_title prefix-matches any of the given titles.

    Strategy:
      1. exact match (normalized)
      2. else: target.startswith(section) match
    Returns up to max_chunks records.
    """
    if not section_titles:
        return []
    target_norm = chunks_df["section_title"].fillna("").map(normalize_section)
    keep_mask = target_norm.eq("")  # all-False seed
    candidates = [normalize_section(s) for s in section_titles if s]
    # exact
    keep_mask |= target_norm.isin(set(candidates))
    # prefix
    for c in candidates:
        if not c:
            continue
        keep_mask |= target_norm.str.startswith(c)
    sub = chunks_df[keep_mask]
    if len(sub) == 0:
        return []
    return sub.head(max_chunks).to_dict("records")
