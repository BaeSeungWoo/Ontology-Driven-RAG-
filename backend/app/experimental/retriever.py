"""Experimental retrieval policies; production retrievers never import this module."""
from pathlib import Path
import re

import numpy as np

from app.core.bm25_tokenizer import tokenize_for_bm25
from app.core.retriever import (
    ChromaRetriever, FAISSRetriever, KGRetriever, LadderRetriever, MultimodalRetriever,
    RetrievalItem, RetrievalResult, _deduplicate_items,
)
from .ocr_page_context import expand_paddle_pages


class ExperimentalRetrieval:
    def _bm25_search(self, query: str, machine_code: str, top_k: int, required_terms=(), source_document="") -> list[dict]:
        bundle = self._bm25_bundle(machine_code)
        if bundle is None:
            return []

        scores = bundle["bm25"].get_scores(tokenize_for_bm25(query))
        order = np.argsort(-scores)
        items: list[dict] = []

        for index in order:
            index = int(index)
            if scores[index] <= 0:
                break
            meta = bundle["metadatas"][index] or {}
            if source_document and meta.get("source_doc_name") != source_document:
                continue
            if machine_code != "ALL" and not self._matches_machine(meta, machine_code):
                continue
            if required_terms and not any(t in bundle["documents"][index].casefold() for t in required_terms):
                continue

            items.append({
                "id": bundle["ids"][index],
                "document": bundle["documents"][index],
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

    def with_page_figures(self, items, machine_code, query=""):
        items = expand_paddle_pages(
            items, Path(__file__).resolve().parents[3] / "pipeline/data", self.config.id)
        return super().with_page_figures(items, machine_code, query)


class ExperimentalChromaRetriever(ExperimentalRetrieval, ChromaRetriever):
    def component_pages(self, machine_code, components, symptoms, limit=24, *, work_target=""):
        """Find evidence even when the subsystem heading and symptom are separate OCR chunks."""
        if machine_code == "ALL" or not components or not symptoms:
            return []
        data = self.machine_search.get(machine_code, where={"document_type": "manual"})
        pages = {}
        for ident, text, meta in zip(data["ids"], data["documents"], data["metadatas"]):
            key = meta.get("source_doc_name"), meta.get("page_range")
            if not all(key):
                continue
            pages.setdefault(key, []).append((ident, text, meta))
        # OCR can separate the naming of the assembly from its inspection on the same page.
        # A word stem also permits inflections within a longer subsystem name.
        stems = {word.removesuffix("ing") for term in components for word in re.findall(r"[a-z]{4,}", term)}
        stems -= {"system", "unit", "device", "mechanism", "assembly", "component", "operation"}
        matches = []
        for rows in pages.values():
            lines = [row[1].casefold() for row in rows]
            parts = [i for i, line in enumerate(lines) if any(t in line for t in components)]
            faults = [i for i, line in enumerate(lines) if any(t in line for t in symptoms)]
            matched_stems = {word for word in stems if any(word in line for line in lines)}
            if not parts and matched_stems:
                parts = [i for i, line in enumerate(lines) if any(word in line for word in matched_stems)]
            if parts and faults:
                distance, pos = min((abs(i-j), j) for i in parts for j in faults)
                ident, text, meta = rows[pos]
                specificity = max((len(t) for t in components if any(t in lines[i] for i in parts)), default=0)
                on_target = bool(work_target and any(work_target in line for line in lines))
                matches.append((not on_target, -len(matched_stems), -specificity, distance, RetrievalItem(ident, text, None, meta)))
        matches.sort(key=lambda hit: hit[:-1])
        return [hit[-1] for hit in matches[:limit]]

    def _vector_search(self, query: str, machine_code: str, top_k: int, where_document=None, source_document="") -> list[dict]:
        query_args = {
            "query_texts": [query],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if machine_code != "ALL":
            query_args["where"] = {"machine_code": {"$contains": machine_code.strip()}}
        if source_document:
            source_filter = {"source_doc_name": source_document}
            query_args["where"] = ({"$and": [query_args["where"], source_filter]}
                                   if "where" in query_args else source_filter)
        if where_document:
            query_args["where_document"] = where_document

        results = self._query_collection(machine_code, **query_args)
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

    def _rank_candidates(self, query: str, machine_code: str, limit: int) -> list[dict]:
        vectors = self._vector_search(query, machine_code, limit)
        if not self.use_bm25:
            return vectors
        return self._rrf_merge(vectors, self._bm25_search(query, machine_code, limit))

    def search(self, query: str, top_k: int = 5, machine_code: str = "ALL",
               intent_query: str = "", **kwargs) -> RetrievalResult:
        top_k = top_k or self.config.vector_db.retrieval_k
        candidate_k = max(top_k * 4, 20)
        if kwargs.get("source_document"):
            source = kwargs["source_document"]
            vectors = self._vector_search(query, machine_code, candidate_k, source_document=source)
            lexical = self._bm25_search(query, machine_code, candidate_k, source_document=source)
            merged_items = self._rrf_merge(vectors, lexical) if self.use_bm25 else vectors
        elif kwargs.get("diagnostic_passages"):
            # Supplement normal retrieval with passages that explicitly describe faults.
            terms = ("malfunction", "Malfunction", "Insufficient", "insufficient", "Possible cause",
                     "possible cause", "Problem", "고장", "원인", "불량", "Störung", "Ursache")
            vectors = self._vector_search(query, machine_code, candidate_k, {"$or": [{"$contains": t} for t in terms]})
            lexical = self._bm25_search(query, machine_code, candidate_k, {t.casefold() for t in terms})
            merged_items = self._rrf_merge(vectors, lexical)
        else:
            merged_items = self._rank_candidates(query, machine_code, candidate_k)
        if intent_query and intent_query != query:
            focused = self._rank_candidates(intent_query, machine_code, candidate_k)
            # Apply the same reciprocal-rank weight to both queries.
            scores = {}
            candidates = {}
            for ranking in (merged_items, focused):
                for rank, item in enumerate(ranking, 1):
                    key = item["id"]
                    candidates.setdefault(key, item)
                    scores[key] = scores.get(key, 0.0) + 1 / (60 + rank)
            merged_items = [dict(candidates[key], query_fusion_score=scores[key])
                            for key in sorted(scores, key=scores.get, reverse=True)]

        raw_items: list[RetrievalItem] = []
        for item in merged_items:
            raw_items.append(
                RetrievalItem(
                    id=item["id"],
                    text=item["document"],
                    score=item.get("similarity"),
                    metadata=item.get("metadata", {}),
                    extra={
                        **({"query_fusion_score": item["query_fusion_score"]} if "query_fusion_score" in item else {}),
                        "distance": item.get("distance"),
                        "similarity": item.get("similarity"),
                        "vector_rank": item.get("vector_rank"),
                        "bm25_rank": item.get("bm25_rank"),
                        "bm25_score": item.get("bm25_score"),
                        "rrf_score": item.get("rrf_score"),
                    },
                )
            )

        if kwargs.get("preserve_variants"):
            # Identical instructions can sit under different model or rating headers.
            pages = {}
            for hit in raw_items:
                key = (hit.metadata.get("source_doc_name"), hit.metadata.get("page_range"))
                if hit.metadata.get("source_type") == "paddleocr" and all(key):
                    pages.setdefault(key, hit)
                else:
                    pages.setdefault(hit.id, hit)
            items = list(pages.values())[:top_k]
        else:
            items = _deduplicate_items(raw_items, top_k)
        return RetrievalResult(items=items, context="")


class ExperimentalFAISSRetriever(ExperimentalRetrieval, FAISSRetriever):
    pass


class ExperimentalKGRetriever(ExperimentalRetrieval, KGRetriever):
    pass


class ExperimentalLadderRetriever(ExperimentalRetrieval, LadderRetriever):
    pass


class ExperimentalMultimodalRetriever(ExperimentalRetrieval, MultimodalRetriever):
    pass

