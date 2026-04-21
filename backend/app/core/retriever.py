# backend/app/core/retriever.py

import httpx
import json
import chromadb
from app.factories.config import Config
from app.embeddings import load_embeddings

class KnowledgeRetriever:
    def __init__(self, config: Config):
        self.config = config

        # Chroma 클라이언트 직접 초기화
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.search_path
        )
        # 임베딩 함수 세팅
        # self.embedding_fn = load_embeddings(config=Config)
        self.embedding_fn = load_embeddings(config=self.config)
        # 컬렉션 세팅
        self.collection = self.chroma.get_or_create_collection(
            # name=self.config.id
            name="test_a",
            embedding_function=self.embedding_fn
        )


    # ------------------------------------------------------------------ #
    #  공개 인터페이스                                                      #
    # ------------------------------------------------------------------ #

    def get_context(self, query: str, mode: str) -> tuple[str, list, list, dict]:
        """LLM에게 전달할 컨텍스트를 생성

        Args:
            query (str): 사용자가 보낸 질문
            mode (str): rag 사용 여부

        Returns:
            tuple[str, list, list, dict]: 검색 결과에 따른 컨텍스트 집합.
        """
        if mode == "base":
            return "", [], [], {}

        # 쿼리 임베딩
        # query_vector = self._embed(query)

        # 벡터 유사도 검색
        results = self.collection.query(
            query_texts=[query],
            n_results=self.config.vector_db.retrieval_k,
            include=["documents", "metadatas", "distances"],
        )

        context_parts = []
        chunk_map: dict[str, str] = {}
        imgs: list[str] = []
        tables: list[str] = []

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            # Chroma distance → similarity (1 - distance)
            # 현재 유사도 validation 주석 처리
            # similarity = 1 - dist
            # if similarity < self.config.vector_db.score_threshold:
            #     continue

            source = meta.get("source_doc_name", "unknown")
            type = meta.get("container_type")
            context_parts.append(f"[문서: {source}]\n{doc}")
            chunk_map[source] = doc

            assets = meta.get("asset_path")

            if assets and type == "pictures":
                imgs.append(assets)
            elif assets and type == "tables":
                tables.append(assets)
            

        context = "\n\n".join(context_parts)

        # Graph-RAG
        if mode == "graph":
            graph_text = self._get_graph_context(query)
            context = f"{context}\n\n[관계 정보]\n{graph_text}"

        return context, imgs, tables, chunk_map

    # ------------------------------------------------------------------ #
    #  내부 메서드                                                          #
    # ------------------------------------------------------------------ #

    # def _embed(self, text: str) -> list[float]:
    #     """Ollama 임베딩 API 호출."""
    #     with httpx.Client(timeout=30) as client:
    #         res = client.post(
    #             self.embed_url,
    #             json={
    #                 "model":  self.embed_model,
    #                 "prompt": text,
    #             },
    #         )
    #         return res.json()["embedding"]

    def _get_graph_context(self, query: str) -> str:
        # TODO: Neo4j 연동 구현
        return "[Graph DB 미연동 — 관계 정보 없음]"