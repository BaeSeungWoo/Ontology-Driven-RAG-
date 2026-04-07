# backend/app/core/retriever.py

import httpx
import json
import chromadb

from app.factories.config import Config


class KnowledgeRetriever:
    def __init__(self, config: Config):
        self.config = config

        # Chroma 클라이언트 직접 초기화
        self.chroma = chromadb.PersistentClient(
            path=config.vector_db.db_path
        )
        self.collection = self.chroma.get_or_create_collection(
            name="documents"
        )

        # 임베딩 서버 URL
        self.embed_url = (
            f"{config.get_embedding_base_url()}/api/embeddings"
        )
        self.embed_model = config.embedding.model

    # ------------------------------------------------------------------ #
    #  공개 인터페이스                                                      #
    # ------------------------------------------------------------------ #

    def get_context(self, query: str, mode: str) -> tuple[str, list, dict]:
        if mode == "base":
            return "", [], {}

        # 쿼리 임베딩
        query_vector = self._embed(query)

        # 벡터 유사도 검색
        results = self.collection.query(
            query_embeddings=[query_vector],
            n_results=self.config.vector_db.retrieval_k,
            include=["documents", "metadatas", "distances"],
        )

        context_parts = []
        chunk_map: dict[str, str] = {}
        imgs: list[str] = []

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            # Chroma distance → similarity (1 - distance)
            similarity = 1 - dist
            if similarity < self.config.vector_db.score_threshold:
                continue

            source = meta.get("source", "unknown")
            context_parts.append(f"[문서: {source}]\n{doc}")
            chunk_map[source] = doc

            if img := meta.get("image_path"):
                imgs.append(img)

        context = "\n\n".join(context_parts)

        # Graph-RAG
        if mode == "graph":
            graph_text = self._get_graph_context(query)
            context = f"{context}\n\n[관계 정보]\n{graph_text}"

        return context, imgs, chunk_map

    # ------------------------------------------------------------------ #
    #  내부 메서드                                                          #
    # ------------------------------------------------------------------ #

    def _embed(self, text: str) -> list[float]:
        """Ollama 임베딩 API 호출."""
        with httpx.Client(timeout=30) as client:
            res = client.post(
                self.embed_url,
                json={
                    "model":  self.embed_model,
                    "prompt": text,
                },
            )
            return res.json()["embedding"]

    def _get_graph_context(self, query: str) -> str:
        # TODO: Neo4j 연동 구현
        return "[Graph DB 미연동 — 관계 정보 없음]"