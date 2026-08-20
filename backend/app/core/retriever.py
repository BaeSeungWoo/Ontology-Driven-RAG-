from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path

import re
import pickle

import chromadb
import faiss
import pandas as pd
import numpy as np
import torch

from app.embeddings import load_embeddings, ColpaliEmbedder
from app.factories.config import Config
from app.core.bm25_tokenizer import tokenize_for_bm25
from app.core.ladder_linker import LadderLinker

from pipeline.ingestion.kg_utils import match_entities, expand_bfs

@dataclass
class RetrievalItem:
    id: str
    text: str
    score: float | None
    metadata: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)

@dataclass
class RetrievalResult:
    items: list[RetrievalItem]
    context: str = ""

def _content_key(document: str) -> str:
    return re.sub(r"\s+", " ", document).strip().lower()

def _deduplicate_items(items: list[RetrievalItem], top_k: int) -> list[RetrievalItem]:
    selected = []
    seen = set()

    for item in items:
        key = _content_key(item.text or "")
        if key in seen:
            continue

        seen.add(key)
        selected.append(item)

        if len(selected) >= top_k:
            break

    return selected

class BaseRetriever(ABC):
    def __init__(self, config: Config):
        self.config = config
        self.embedding_fn = load_embeddings(self.config)

    @abstractmethod
    def search(self, query: str, top_k: int = 5, machine_code: str = "ALL", **kwargs) -> RetrievalResult:
        pass    

    def _load_bm25(self):
        bm25_path = Path(self.config.vector_db.get_search_path("bm25")) / "bm25_bundle.pkl"
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25 bundle not found: {bm25_path}")
        with bm25_path.open("rb") as f:
            return pickle.load(f)

    def _bm25_search(self, query: str, machine_code: str, top_k: int) -> list[dict]:
        if self.bm25 is None:
            return []

        scores = self.bm25["bm25"].get_scores(tokenize_for_bm25(query))
        order = np.argsort(-scores)
        items: list[dict] = []

        for index in order:
            index = int(index)
            meta = self.bm25["metadatas"][index] or {}
            if machine_code != "ALL" and not self._matches_machine(meta, machine_code):
                continue

            items.append({
                "id": self.bm25["ids"][index],
                "document": self.bm25["documents"][index],
                "metadata": meta,
                "distance": None,
                "similarity": None,
                "bm25_score": float(scores[index]),
                "vector_rank": None,
                "bm25_rank": len(items) + 1,
            })

            if len(items) >= top_k:
                break

        return items

    def _matches_machine(self, meta: dict, machine_code: str) -> bool:
        target = machine_code.strip()
        value = meta.get("machine_code")

        if value is None:
            return False

        if isinstance(value, str):
            return target in value

        if isinstance(value, (list, tuple, set)):
            return any(target == str(v).strip() for v in value if v is not None)

        if isinstance(value, np.ndarray):
            return any(target == str(v).strip() for v in value.tolist() if v is not None)

        return target in str(value)

    def _rrf_merge(self, vector_items: list[dict], bm25_items: list[dict], rrf_k: int = 60) -> list[dict]:
        merged: dict[str, dict] = {}

        for source_name, items in (("vector", vector_items), ("bm25", bm25_items)):
            for rank, item in enumerate(items, start=1):
                chunk_id = item["id"]
                if chunk_id not in merged:
                    merged[chunk_id] = {**item, "rrf_score": 0.0}

                merged[chunk_id]["rrf_score"] += 1.0 / (rrf_k + rank)
                merged[chunk_id][f"{source_name}_rank"] = rank

                if source_name == "vector":
                    merged[chunk_id]["distance"] = item.get("distance")
                    merged[chunk_id]["similarity"] = item.get("similarity")
                else:
                    merged[chunk_id]["bm25_score"] = item.get("bm25_score")

        return sorted(
            merged.values(),
            key=lambda item: item["rrf_score"],
            reverse=True,
        )

    def _load_chunks_df(self) -> pd.DataFrame:
        chunks_path = Path(self.config.vector_db.get_search_path("faiss")) / "chunks.parquet"
        if not chunks_path.exists():
            raise FileNotFoundError(f"Chunks parquet not found: {chunks_path}")
        return pd.read_parquet(chunks_path)

    def _to_json_safe(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._to_json_safe(v) for k, v in value.items()}

        if isinstance(value, list):
            return [self._to_json_safe(v) for v in value]

        if isinstance(value, tuple):
            return [self._to_json_safe(v) for v in value]

        if isinstance(value, set):
            return [self._to_json_safe(v) for v in value]

        if isinstance(value, np.ndarray):
            return [self._to_json_safe(v) for v in value.tolist()]

        if isinstance(value, np.integer):
            return int(value)

        if isinstance(value, np.floating):
            return float(value)

        if isinstance(value, np.bool_):
            return bool(value)

        return value

    def get_context(self, query: str, machine_code: str = "ALL") -> tuple[str, list[str], list[str], list[dict]]:
        result = self.search(query=query, machine_code=machine_code)

        context_parts = []
        imgs = []
        tables = []
        chunks = []

        for index, item in enumerate(result.items, start=1):
            meta = item.metadata
            safe_meta = self._to_json_safe(meta)
            source = safe_meta.get("source_doc_name", "unknown")
            container_type = safe_meta.get("container_type", "texts")
            asset_path = safe_meta.get("asset_path")

            context_parts.append(f"[chunk:{index}]\n[문서: {source}]\n{item.text}")

            chunks.append({
                "index": index,
                "retrieval_rank": index,
                "document": item.text,
                "metadata": safe_meta,
                **item.extra,
            })

            if asset_path and container_type == "pictures":
                imgs.append(asset_path)
            elif asset_path and container_type == "tables":
                tables.append(asset_path)

        context = "\n\n".join(context_parts)

        if result.context:
            context = f"{context}\n\n[참고 정보]\n{result.context}" if context else f"[참고 정보]\n{result.context}"

        return context, imgs, tables, chunks

class ChromaRetriever(BaseRetriever):
    def __init__(self, config: Config, use_bm25: bool = False):
        super().__init__(config)
        self.use_bm25 = use_bm25
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.get_search_path("chroma")
        )
        self.collection = self.chroma.get_or_create_collection(
            name=self.config.id,
            embedding_function=self.embedding_fn
        )
        self.bm25 = self._load_bm25() if self.use_bm25 else None

    def _vector_search(self, query: str, machine_code: str, top_k: int) -> list[dict]:
        query_args = {
            "query_texts": [query],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if machine_code != "ALL":
            query_args["where"] = {"machine_code": {"$contains": machine_code.strip()}}

        results = self.collection.query(**query_args)
        items: list[dict] = []

        for rank, (chunk_id, doc, meta, dist) in enumerate(
            zip(
                results.get("ids", [[]])[0],
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
                results.get("distances", [[]])[0],
            ),
            start=1,
        ):
            distance = float(dist) if dist is not None else None
            items.append({
                "id": chunk_id,
                "document": doc,
                "metadata": meta or {},
                "distance": distance,
                "similarity": (1 - distance) if distance is not None else None,
                "bm25_score": None,
                "vector_rank": rank,
                "bm25_rank": None,
                "rrf_score": None,
            })

        return items

    def search(self, query: str, top_k: int = 5, machine_code: str = "ALL",**kwargs) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k
        candidate_k = max(top_k * 4, 20)

        vector_items = self._vector_search(query, machine_code, candidate_k)

        if self.use_bm25:
            bm25_items = self._bm25_search(query, machine_code, candidate_k)
            merged_items = self._rrf_merge(vector_items, bm25_items)
        else:
            merged_items = vector_items

        raw_items: list[RetrievalItem] = []
        for item in merged_items:
            raw_items.append(
                RetrievalItem(
                    id=item["id"],
                    text=item["document"],
                    score=item.get("similarity"),
                    metadata=item.get("metadata", {}),
                    extra={
                        "distance": item.get("distance"),
                        "similarity": item.get("similarity"),
                        "vector_rank": item.get("vector_rank"),
                        "bm25_rank": item.get("bm25_rank"),
                        "bm25_score": item.get("bm25_score"),
                        "rrf_score": item.get("rrf_score"),
                    },
                )
            )

        items = _deduplicate_items(raw_items, top_k)
        return RetrievalResult(items=items, context="")

class LadderRetriever(BaseRetriever):
    def __init__(self, config: Config):
        super().__init__(config)
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.get_search_path("chroma")
        )
        self.collection = self.chroma.get_or_create_collection(
            name=self.config.id,
            embedding_function=self.embedding_fn,
        )
        self.bm25 = self._load_bm25()
        project_root = Path(__file__).resolve().parents[3]
        structure_dir = project_root / "pipeline" / "data" / self.config.id / "ladder" / "struct"
        self.ladder_linker = LadderLinker(structure_dir)

    def _where_for_container(self, container_type: str, machine_code: str) -> dict:
        container_filter = (
            {"container_type": "ladder"}
            if container_type == "ladder"
            else {"container_type": {"$ne": "ladder"}}
        )

        if machine_code == "ALL":
            return container_filter

        return {
            "$and": [
                container_filter,
                {"machine_code": {"$contains": machine_code.strip()}},
            ]
        }

    def _vector_search(
        self,
        query: str,
        machine_code: str,
        top_k: int,
        container_type: str,
    ) -> list[dict]:
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=self._where_for_container(container_type, machine_code),
            include=["documents", "metadatas", "distances"],
        )

        items: list[dict] = []
        for rank, (chunk_id, doc, meta, dist) in enumerate(
            zip(
                results.get("ids", [[]])[0],
                results.get("documents", [[]])[0],
                results.get("metadatas", [[]])[0],
                results.get("distances", [[]])[0],
            ),
            start=1,
        ):
            distance = float(dist) if dist is not None else None
            items.append({
                "id": chunk_id,
                "document": doc,
                "metadata": meta or {},
                "distance": distance,
                "similarity": (1 - distance) if distance is not None else None,
                "bm25_score": None,
                "vector_rank": rank,
                "bm25_rank": None,
                "rrf_score": None,
            })

        return items

    def _bm25_search_by_container(
        self,
        query: str,
        machine_code: str,
        top_k: int,
        container_type: str,
    ) -> list[dict]:
        if self.bm25 is None:
            return []

        scores = self.bm25["bm25"].get_scores(tokenize_for_bm25(query))
        order = np.argsort(-scores)
        items: list[dict] = []

        for index in order:
            index = int(index)
            meta = self.bm25["metadatas"][index] or {}
            is_ladder = meta.get("container_type") == "ladder"
            if (container_type == "ladder") != is_ladder:
                continue
            if machine_code != "ALL" and not self._matches_machine(meta, machine_code):
                continue

            items.append({
                "id": self.bm25["ids"][index],
                "document": self.bm25["documents"][index],
                "metadata": meta,
                "distance": None,
                "similarity": None,
                "bm25_score": float(scores[index]),
                "vector_rank": None,
                "bm25_rank": len(items) + 1,
            })
            if len(items) >= top_k:
                break

        return items

    def _search_container(
        self,
        query: str,
        machine_code: str,
        top_k: int,
        container_type: str,
    ) -> list[RetrievalItem]:
        candidate_k = max(top_k * 4, 20)
        vector_items = self._vector_search(query, machine_code, candidate_k, container_type)
        bm25_items = self._bm25_search_by_container(query, machine_code, candidate_k, container_type)
        merged_items = self._rrf_merge(vector_items, bm25_items)
        retrieval_group = "ladder" if container_type == "ladder" else "document"

        raw_items = [
            RetrievalItem(
                id=item["id"],
                text=item["document"],
                score=item.get("similarity"),
                metadata=item.get("metadata", {}),
                extra={
                    "retrieval_group": retrieval_group,
                    "distance": item.get("distance"),
                    "similarity": item.get("similarity"),
                    "vector_rank": item.get("vector_rank"),
                    "bm25_rank": item.get("bm25_rank"),
                    "bm25_score": item.get("bm25_score"),
                    "rrf_score": item.get("rrf_score"),
                },
            )
            for item in merged_items
        ]
        return _deduplicate_items(raw_items, top_k)

    def _profile_ladder_items(
        self,
        seed_nblocks: list[str],
        machine_code: str,
    ) -> list[RetrievalItem]:
        items = []
        for nblock in seed_nblocks:
            where = self._where_for_container("ladder", machine_code)
            if "$and" in where:
                where = {"$and": [*where["$and"], {"section_title": nblock}]}
            else:
                where = {"$and": [where, {"section_title": nblock}]}

            result = self.collection.get(
                where=where,
                include=["documents", "metadatas"],
            )
            for chunk_id, document, metadata in zip(
                result.get("ids", []),
                result.get("documents", []),
                result.get("metadatas", []),
            ):
                items.append(RetrievalItem(
                    id=chunk_id,
                    text=document,
                    score=None,
                    metadata=metadata or {},
                    extra={
                        "retrieval_group": "ladder",
                        "profile_seed": True,
                    },
                ))
        return items

    def search(
        self,
        query: str,
        top_k: int = 5,
        machine_code: str = "ALL",
        intent_type: str = "troubleshooting",
        **kwargs,
    ) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k
        query_plan = self.ladder_linker.build_query_plan(query)
        search_query = query_plan["expanded_query"]
        ladder_limit = max(top_k, len(query_plan["seed_nblocks"]))
        document_items = self._search_container(search_query, machine_code, top_k, "document")
        ladder_candidates = self._search_container(search_query, machine_code, max(ladder_limit * 4, 20), "ladder")
        seeded_items = self._profile_ladder_items(query_plan["seed_nblocks"], machine_code)
        ladder_items = _deduplicate_items([*seeded_items, *ladder_candidates], max(ladder_limit * 4, 20))
        linked_addresses = self.ladder_linker.linked_addresses(
            question=query,
            document_texts=[item.text for item in document_items],
            profile_addresses=query_plan["addresses"],
        )
        ladder_items = self.ladder_linker.rerank(
            ladder_items,
            linked_addresses,
            seed_nblocks=query_plan["seed_nblocks"],
        )[:ladder_limit]
        trace_roots = ladder_items[:2]
        for item in trace_roots:
            item.extra["trace_root"] = True

        trace_lines = self.ladder_linker.trace(trace_roots, intent_type=intent_type)

        return RetrievalResult(
            items=[*document_items, *ladder_items],
            context="\n".join(trace_lines),
        )

    def get_context(
        self,
        query: str,
        machine_code: str = "ALL",
        intent_type: str = "troubleshooting",
    ):
        result = self.search(
            query=query,
            machine_code=machine_code,
            intent_type=intent_type,
        )
        grouped_items = {
            "document": [item for item in result.items if item.extra.get("retrieval_group") == "document"],
            "ladder": [item for item in result.items if item.extra.get("retrieval_group") == "ladder"],
        }

        context_sections = []
        imgs = []
        tables = []
        chunks = []
        index = 0

        for group, title in (("document", "문서 근거"), ("ladder", "래더 근거")):
            parts = []
            for item in grouped_items[group]:
                index += 1
                meta = self._to_json_safe(item.metadata)
                source = meta.get("source_doc_name", "unknown")
                container_type = meta.get("container_type", "texts")
                asset_path = meta.get("asset_path")
                parts.append(f"[chunk:{index}]\n[문서: {source}]\n{item.text}")
                chunks.append({
                    "index": index,
                    "retrieval_rank": index,
                    "document": item.text,
                    "metadata": meta,
                    **item.extra,
                })

                if asset_path and container_type == "pictures":
                    imgs.append(asset_path)
                elif asset_path and container_type == "tables":
                    tables.append(asset_path)

            if parts:
                context_sections.append(f"[{title}]\n" + "\n\n".join(parts))

        if result.context:
            context_sections.append(result.context)

        context_payload = "\n\n".join(context_sections), imgs, tables, chunks
        return context_payload

class FAISSRetriever(BaseRetriever):
    def __init__(self, config: Config, use_bm25: bool = False):
        super().__init__(config)
        self.use_bm25 = use_bm25
        self.faiss_index = self._load_faiss_index()
        self.chunks_df = self._load_chunks_df()
        self.bm25 = self._load_bm25() if self.use_bm25 else None

    def _load_faiss_index(self):
        faiss_path = Path(self.config.vector_db.get_search_path("faiss")) / "faiss.index"
        if not faiss_path.exists():
            raise FileNotFoundError(f"FAISS index not found: {faiss_path}")
        return faiss.read_index(str(faiss_path))

    def _embed_query(self, query: str) -> np.ndarray:
        passage = f"passage: {query}"
        raw = self.embedding_fn([passage])
        arr = np.asarray(raw, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(arr)
        return arr

    def _vector_search(self, query: str, machine_code: str, top_k: int) -> list[dict]:
        query_vec = self._embed_query(query)
        scores, indices = self.faiss_index.search(query_vec, top_k)

        items: list[dict] = []

        for rank, (idx, score) in enumerate(zip(indices[0], scores[0]), start=1):
            if idx < 0:
                continue

            row = self.chunks_df.iloc[int(idx)].to_dict()
            meta = row.get("metadata") or {}

            if machine_code != "ALL" and not self._matches_machine(meta, machine_code):
                continue

            doc = str(row.get("page_content") or "").strip()
            row_id = str(row.get("id") or "").strip()
            meta_chunk_id = str(meta.get("chunk_id") or "").strip()
            chunk_id = row_id or meta_chunk_id or str(idx)

            items.append({
                "id": chunk_id,
                "document": doc,
                "metadata": meta,
                "distance": None,
                "similarity": float(score),
                "bm25_score": None,
                "vector_rank": rank,
                "bm25_rank": None,
            })

        return items

    def search(self, query: str, top_k: int = 5, machine_code: str = "ALL", **kwargs) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k
        candidate_k = max(top_k * 4, 20)

        vector_items = self._vector_search(query, machine_code, candidate_k)

        if self.use_bm25:
            bm25_items = self._bm25_search(query, machine_code, candidate_k)
            merged_items = self._rrf_merge(vector_items, bm25_items)
        else:
            merged_items = vector_items

        raw_items: list[RetrievalItem] = []
        for item in merged_items:
            raw_items.append(
                RetrievalItem(
                    id=item["id"],
                    text=item["document"],
                    score=item.get("similarity"),
                    metadata=item.get("metadata", {}),
                    extra={
                        "distance": item.get("distance"),
                        "similarity": item.get("similarity"),
                        "vector_rank": item.get("vector_rank"),
                        "bm25_rank": item.get("bm25_rank"),
                        "bm25_score": item.get("bm25_score"),
                        "rrf_score": item.get("rrf_score"),
                    },
                )
            )

        items = _deduplicate_items(raw_items, top_k)
        return RetrievalResult(items=items, context="")

class KGRetriever(BaseRetriever):
    def __init__(self, config: Config):
        super().__init__(config)
        self.kg = self._load_kg()

    def _load_kg(self):
        kg_path = Path(self.config.vector_db.get_search_path("kg")) / "kg.pkl"
        if not kg_path.exists():
            raise FileNotFoundError(f"KG bundle not found: {kg_path}")
        with kg_path.open("rb") as f:
            return pickle.load(f)

    def _embed_query(self, query: str) -> np.ndarray:
        passage = f"passage: {query}"
        raw = self.embedding_fn([passage])
        arr = np.asarray(raw, dtype=np.float32).reshape(1, -1)
        faiss.normalize_L2(arr)
        return arr[0]

    def search(
        self,
        query: str,
        top_k: int = 5,
        machine_code: str = "ALL",
        **kwargs,
    ) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k

        g = self.kg["g"]
        entity_list = self.kg["entity_list"]
        entity_embs = self.kg["entity_embs"]
        triple_embs = self.kg["triple_embs"]
        edge_to_row = self.kg["edge_to_row"]

        query_emb = self._embed_query(query)

        seeds = match_entities(
            query_emb=query_emb,
            entity_embs=entity_embs,
            entity_list=entity_list,
            top_k=max(top_k, 5),
            min_score=0.5,
        )
        seed_entities = [name for name, _ in seeds]
        print(f"seed_entities: {seed_entities}")

        if not seed_entities:
            return RetrievalResult(items=[], context="")

        triples, _sections, graph_scores = expand_bfs(
            g=g,
            seeds=seed_entities,
            query_emb=query_emb,
            triple_embs=triple_embs,
            edge_to_row=edge_to_row,
            max_triples=max(top_k * 4, 20),
            min_edge_score=0.30,
            max_depth=4,
        )

        raw_items: list[RetrievalItem] = []

        for rank, (triple, score) in enumerate(zip(triples, graph_scores), start=1):
            s, p, o = triple

            matched_meta = None
            matched_chunk_id = None
            matched_doc_name = ""
            matched_section_title = ""
            matched_page_range = ""
            matched_machine_code = None

            for u, v, k, d in g.edges(keys=True, data=True):
                surface = d.get("surface")
                if surface != triple:
                    continue

                chunk_ids = sorted(d.get("chunk_ids") or [])
                sections = sorted(d.get("sections") or [])
                edge_machine_code = d.get("machine_code")

                if chunk_ids:
                    matched_chunk_id = chunk_ids[0]

                if sections:
                    matched_section_title = sections[0]

                candidate_passage_nodes = []
                for entity_node in (u, v):
                    if not g.has_node(entity_node):
                        continue

                    for _, nb, _k2, d2 in g.out_edges(entity_node, keys=True, data=True):
                        if d2.get("predicate") != "appears_in":
                            continue
                        if not g.has_node(nb):
                            continue
                        nb_data = g.nodes[nb]
                        if nb_data.get("kind") != "passage":
                            continue
                        candidate_passage_nodes.append(nb)

                for passage_node in candidate_passage_nodes:
                    node_data = g.nodes[passage_node]
                    node_chunk_id = str(node_data.get("chunk_id") or "").strip()

                    if matched_chunk_id and node_chunk_id != matched_chunk_id:
                        continue

                    matched_chunk_id = matched_chunk_id or node_chunk_id
                    matched_doc_name = str(node_data.get("doc_name") or "").strip()
                    matched_section_title = matched_section_title or str(node_data.get("section_title") or "").strip()
                    matched_page_range = str(node_data.get("page_range") or "").strip()
                    matched_machine_code = node_data.get("machine_code")
                    break

                matched_machine_code = matched_machine_code or edge_machine_code

                matched_meta = {
                    "chunk_id": str(matched_chunk_id or "").strip(),
                    "source_doc_name": matched_doc_name,
                    "section_title": matched_section_title,
                    "page_range": matched_page_range,
                    "machine_code": matched_machine_code,
                }
                break

            if machine_code != "ALL":
                if not matched_meta or not self._matches_machine(matched_meta, machine_code):
                    continue

            text_lines = [
                f"[triple] ({s}, {p}, {o})",
            ]
            if matched_section_title:
                text_lines.append(f"[section] {matched_section_title}")
            if matched_doc_name:
                text_lines.append(f"[document] {matched_doc_name}")
            if matched_page_range:
                text_lines.append(f"[pages] {matched_page_range}")
            if matched_chunk_id:
                text_lines.append(f"[chunk_id] {matched_chunk_id}")

            raw_items.append(
                RetrievalItem(
                    id=str(matched_chunk_id or f"triple-{rank}"),
                    text="\n".join(text_lines),
                    score=float(score),
                    metadata=matched_meta or {},
                    extra={
                        "similarity": float(score),
                        "graph_rank": rank,
                        "seed_entities": seed_entities,
                        "triple": [s, p, o],
                        "section": matched_section_title,
                        "doc_name": matched_doc_name,
                        "page_range": matched_page_range,
                        "chunk_id": matched_chunk_id,
                    },
                )
            )

        items = _deduplicate_items(raw_items, top_k)

        graph_context_lines = []
        for item in items:
            triple = item.extra.get("triple")
            sim = item.extra.get("similarity")
            if triple:
                graph_context_lines.append(
                    f"- ({triple[0]}, {triple[1]}, {triple[2]}) score={sim:.4f}"
                )

        return RetrievalResult(
            items=items,
            context="\n".join(graph_context_lines),
        )

class MultimodalRetriever(BaseRetriever):
    def __init__(self, config: Config):
        super().__init__(config)
        self.mm_embs, self.mm_meta = self._load_multimodal_index()
        self.encoder = ColpaliEmbedder()
        self.chunks_df = self._load_chunks_df()

    def _load_multimodal_index(self) -> tuple[list[torch.Tensor], pd.DataFrame]:
        mm_path = Path(self.config.vector_db.get_search_path("multimodal"))
        emb_path = mm_path / "img_emb.pt"
        meta_path = mm_path / "img_meta.parquet"

        if not emb_path.exists():
            raise FileNotFoundError(f"Multimodal embeddings not found: {emb_path}")
        if not meta_path.exists():
            raise FileNotFoundError(f"Multimodal metadata not found: {meta_path}")

        return torch.load(emb_path, weights_only=False), pd.read_parquet(meta_path)

    def _page_matches(self, page_range: str, page_num: int | None) -> bool:
        if page_num is None:
            return True

        raw = str(page_range or "").strip()
        if not raw:
            return False

        target = int(page_num)

        if raw.isdigit():
            return int(raw) == target

        if "-" in raw:
            left, right = raw.split("-", 1)
            left = left.strip()
            right = right.strip()

            if left.isdigit() and right.isdigit():
                start = int(left)
                end = int(right)
                return start <= target <= end

        if "," in raw:
            parts = [p.strip() for p in raw.split(",")]
            return any(p.isdigit() and int(p) == target for p in parts)

        return raw == str(target)

    def _find_page_chunks(self, page_num: int | None) -> list[dict[str, Any]]:
        matched_chunks: list[dict[str, Any]] = []

        for _, chunk_row in self.chunks_df.iterrows():
            chunk_dict = chunk_row.to_dict()
            chunk_meta = chunk_dict.get("metadata") or {}
            chunk_page_range = chunk_dict.get("page_range") or chunk_meta.get("page_range")

            if self._page_matches(chunk_page_range, page_num):
                matched_chunks.append(chunk_dict)

        return matched_chunks

    def search(
        self,
        query: str,
        top_k: int = 5,
        machine_code: str = "ALL",
        **kwargs,
    ) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k

        query_emb = self.encoder.embed_query(query)
        scores = self.encoder.score(query_emb, self.mm_embs)

        rows = self.mm_meta.to_dict("records")

        scored_rows: list[dict[str, Any]] = []

        for row, score in zip(rows, scores):
            row_copy = dict(row)
            row_copy["_score"] = float(score)
            scored_rows.append(row_copy)

        scored_rows.sort(key=lambda item: item["_score"], reverse=True)
        candidate_k = max(top_k * 5, 20)
        scored_rows = scored_rows[:candidate_k]

        raw_items = []

        for rank, row in enumerate(scored_rows, start=1):
            doc_name = str(row.get("source_doc_name") or "").strip()
            page_num = row.get("page_num")
            image_path = str(row.get("image_path") or "").strip()
            row_machine_code = row.get("machine_code")

            # if machine_code != "ALL" and not self._matches_machine(
            #     {"machine_code": row_machine_code},
            #     machine_code,
            # ):
            #     continue

            matched_chunks = self._find_page_chunks(page_num)

            section_titles: list[str] = []
            seen_titles: set[str] = set()
            chunk_ids: list[str] = []
            chunk_texts: list[str] = []

            for matched_chunk in matched_chunks:
                chunk_meta = matched_chunk.get("metadata") or {}
                section_title = str(chunk_meta.get("section_title") or "").strip()
                chunk_id = str(chunk_meta.get("chunk_id") or "").strip()
                chunk_text = str(matched_chunk.get("page_content") or "").strip()

                if section_title and section_title not in seen_titles:
                    seen_titles.add(section_title)
                    section_titles.append(section_title)

                if chunk_id:
                    chunk_ids.append(chunk_id)

                if chunk_text:
                    chunk_texts.append(chunk_text)

            section_title_text = " / ".join(section_titles)
            chunk_text = "\n\n".join(chunk_texts)

            text_parts = [f"[이미지: {image_path}]"]
            if section_title_text:
                text_parts.append(f"[{section_title_text}]")
            if chunk_text:
                text_parts.append(chunk_text)

            raw_items.append(
                RetrievalItem(
                    id=f"{doc_name}:{page_num or rank}",
                    text=" ".join(text_parts),
                    score=float(row["_score"]),
                    metadata={
                        "source_doc_name": doc_name,
                        "page_range": str(page_num or "").strip(),
                        "asset_path": image_path,
                        "container_type": "pictures",
                        "machine_code": row_machine_code,
                        "section_title": section_title_text,
                        "chunk_ids": chunk_ids,
                    },
                    extra={
                        "similarity": float(row["_score"]),
                        "image_path": image_path,
                        "page_num": page_num,
                        "source_path": row.get("source_path"),
                        "doc_type": row.get("doc_type"),
                    },
                )
            )

        items = raw_items[:top_k]
        return RetrievalResult(items=items, context="")
