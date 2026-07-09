# backend/app/core/retriever.py

import pickle
import re
from pathlib import Path

import chromadb
import numpy as np

from app.core.bm25_tokenizer import tokenize_for_bm25
from app.factories.config import Config
from app.embeddings import load_embeddings


def _content_key(document: str) -> str:
    return re.sub(r"\s+", " ", document).strip().lower()


def _deduplicate_by_content(items: list[dict], top_k: int) -> list[dict]:
    selected: list[dict] = []
    seen: set[str] = set()

    for item in items:
        key = _content_key(item.get("document") or "")
        if key in seen:
            continue

        seen.add(key)
        selected.append(item)
        if len(selected) >= top_k:
            break

    return selected


class KnowledgeRetriever:
    def __init__(self, config: Config):
        self.config = config
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.get_search_path("chroma")
        )
        self.embedding_fn = load_embeddings(config=self.config)

        self.collection = self.chroma.get_or_create_collection(
            name=self.config.id,
            embedding_function=self.embedding_fn,
        )

    def get_context(self, query: str, mode: str, machine_code: str = "ALL") -> tuple[str, list, list, list]:
        """Build retrieval context and metadata for LLM + UI."""
        if mode == "base":
            return "", [], [], []

        top_k = self.config.vector_db.retrieval_k
        candidate_k = max(top_k * 4, 20)

        if machine_code == "ALL":
            results = self.collection.query(
                query_texts=[query],
                n_results=candidate_k,
                include=["documents", "metadatas", "distances"],
            )
        else:
            results = self.collection.query(
                query_texts=[query],
                n_results=candidate_k,
                include=["documents", "metadatas", "distances"],
                where={"machine_code": {"$contains": machine_code.strip()}}
            )

        context_parts: list[str] = []
        chunks: list[dict] = []
        imgs: list[str] = []
        tables: list[str] = []

        items = _deduplicate_by_content([
            {
                "document": doc,
                "metadata": meta or {},
                "distance": float(dist) if dist is not None else None,
            }
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            )
        ], top_k)

        for index, item in enumerate(items, start=1):
            doc = item["document"]
            meta = item["metadata"]
            dist = item["distance"]
            source = meta.get("source_doc_name", "unknown")
            container_type = meta.get("container_type")
            similarity = (1 - dist) if dist is not None else None

            context_parts.append(f"[chunk:{index}]\n[문서: {source}]\n{doc}")

            chunks.append({
                "index": index,
                "retrieval_rank": index,
                "document": doc,
                "metadata": meta,
                "distance": dist,
                "similarity": similarity,
            })

            asset_path = meta.get("asset_path")
            if asset_path and container_type == "pictures":
                imgs.append(asset_path)
            elif asset_path and container_type == "tables":
                tables.append(asset_path)

        context = "\n\n".join(context_parts)

        print(chunks)

        if mode == "graph":
            graph_text = self._get_graph_context(query)
            context = f"{context}\n\n[참고 정보]\n{graph_text}"

        return context, imgs, tables, chunks

    def _get_graph_context(self, query: str) -> str:
        # TODO: Neo4j integration
        return "[Graph DB 미연동 - 관계 정보 없음]"


class HybridKnowledgeRetriever:
    def __init__(self, config: Config, bm25_path: str | None = None):
        self.config = config
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.get_search_path("chroma")
        )
        self.embedding_fn = load_embeddings(config=self.config)
        
        self.collection = self.chroma.get_or_create_collection(
            name=self.config.id,
            embedding_function=self.embedding_fn,
        )
        # BM25 추가
        self.bm25_path = Path(bm25_path) if bm25_path else self._default_bm25_path()
        self.bm25_bundle = self._load_bm25_bundle(self.bm25_path)

    def get_context(self, query: str, mode: str, machine_code: str = "ALL") -> tuple[str, list, list, list]:
        if mode == "base":
            return "", [], [], []

        top_k = self.config.vector_db.retrieval_k
        candidate_k = max(top_k * 4, 20) # 후보 수
        # 의미기반 검색후보
        vector_items = self._vector_search(query, machine_code, candidate_k) 
        # 키워드기반 검색후보
        bm25_items = self._bm25_search(query, machine_code, candidate_k)
        # RRF 점수 방식으로 의미기반+키워드기반 최종후보 결정 
        merged_items = self._rrf_merge(vector_items, bm25_items, top_k) 

        context_parts: list[str] = []
        chunks: list[dict] = []
        imgs: list[str] = []
        tables: list[str] = []

        # context 생성
        for index, item in enumerate(merged_items, start=1):
            doc = item["document"]
            meta = item["metadata"]
            source = meta.get("source_doc_name", "unknown")
            container_type = meta.get("container_type")

            context_parts.append(f"[chunk:{index}]\n[문서: {source}]\n{doc}")
            chunks.append({
                "index": index,
                "retrieval_rank": index,
                "document": doc,
                "metadata": meta,
                "distance": item.get("distance"),
                "similarity": item.get("similarity"),
                # 디버깅용 필드 추가
                "vector_rank": item.get("vector_rank"),
                "bm25_rank": item.get("bm25_rank"),
                "bm25_score": item.get("bm25_score"),
                "rrf_score": item.get("rrf_score"),
            })

            asset_path = meta.get("asset_path")
            if asset_path and container_type == "pictures":
                imgs.append(asset_path)
            elif asset_path and container_type == "tables":
                tables.append(asset_path)

        context = "\n\n".join(context_parts)
        
        if mode == "graph":
            context = f"{context}\n\n[참고 정보]\n{self._get_graph_context(query)}"

        return context, imgs, tables, chunks

    # ----- BM25 번들파일 경로, load -----
    def _default_bm25_path(self) -> Path:
        return Path(self.config.vector_db.get_search_path("bm25")) / "bm25_bundle.pkl"

    def _load_bm25_bundle(self, bm25_path: Path) -> dict:
        if not bm25_path.exists():
            raise FileNotFoundError(f"BM25 bundle not found: {bm25_path}")
        with bm25_path.open("rb") as f:
            return pickle.load(f)
    # -----------------------------------

    # ----- machine_code 필터 -----
    # Vector: Chroma DB query 단계에서 where 필터
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
            })

        return items

    # BM25: 점수 계산 후 metadata를 직접 검사해서 continue
    def _bm25_search(self, query: str, machine_code: str, top_k: int) -> list[dict]:
        scores = self.bm25_bundle["bm25"].get_scores(tokenize_for_bm25(query))
        order = np.argsort(-scores)
        items: list[dict] = []

        for index in order:
            index = int(index)
            meta = self.bm25_bundle["metadatas"][index] or {}
            if machine_code != "ALL" and not self._matches_machine(meta, machine_code):
                continue

            items.append({
                "id": self.bm25_bundle["ids"][index],
                "document": self.bm25_bundle["documents"][index],
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
        value = meta.get("machine_code")
        if isinstance(value, list):
            return machine_code.strip() in value
        return machine_code.strip() in str(value or "")

    # -----------------------------

    def _rrf_merge(self, vector_items: list[dict], bm25_items: list[dict], top_k: int, rrf_k: int = 60) -> list[dict]:
        merged: dict[str, dict] = {}

        # Vector 결과와 BM25 결과를 모두 돌면서 같은 chunk_id를 기준으로 합칩니다.
        for source_name, items in (("vector", vector_items), ("bm25", bm25_items)):
            # RRF 점수 병합 로직
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
        # 병합 후 최종 k개 후보 반환
        ranked_items = sorted(merged.values(), key=lambda item: item["rrf_score"], reverse=True)
        return _deduplicate_by_content(ranked_items, top_k)

    def _get_graph_context(self, query: str) -> str:
        # TODO: Neo4j integration
        return "[Graph DB 미연동 - 관계 정보 없음]"
