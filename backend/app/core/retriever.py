# backend/app/core/retriever.py

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import OllamaEmbeddings

from app.factories.config import Config


class KnowledgeRetriever:
    def __init__(self, config: Config):
        self.config = config
        self.embeddings = OllamaEmbeddings(
            model=config.embedding.model,
            base_url=config.get_embedding_base_url(),
        )
        self.vector_db = Chroma(
            persist_directory=config.vector_db.db_path,
            embedding_function=self.embeddings,
        )

    # ------------------------------------------------------------------ #
    #  service.py → prepare_context / ask 에서 호출하는 공개 인터페이스     #
    # ------------------------------------------------------------------ #

    def get_context(self, query: str, mode: str) -> tuple[str, list, dict]:
        """
        mode에 따라 컨텍스트 문자열, 이미지 목록, 청크 맵을 반환합니다.

        Returns:
            context   : LLM 프롬프트에 삽입할 텍스트
            imgs      : 관련 이미지 경로 목록 (미구현 시 빈 리스트)
            chunk_map : {출처: 내용} 매핑 딕셔너리 (인용 추적용)
        """
        if mode == "base":
            return "", [], {}

        # ── RAG: 벡터 유사도 검색 ──────────────────────────────────────
        docs_with_score = self.vector_db.similarity_search_with_score(
            query,
            k=self.config.vector_db.retrieval_k,
        )

        context_parts = []
        chunk_map: dict[str, str] = {}
        imgs: list[str] = []

        for doc, score in docs_with_score:
            # score_threshold 미만인 문서는 제외
            if score < self.config.vector_db.score_threshold:
                continue

            source = doc.metadata.get("source", "unknown")
            content = doc.page_content
            context_parts.append(f"[문서: {source}]\n{content}")
            chunk_map[source] = content

            # 이미지 경로가 메타데이터에 있으면 수집
            if img := doc.metadata.get("image_path"):
                imgs.append(img)

        context = "\n\n".join(context_parts)

        # ── Graph-RAG: 벡터 컨텍스트에 관계 정보 추가 ─────────────────
        if mode == "graph":
            graph_text = self._get_graph_context(query)
            context = f"{context}\n\n[관계 정보]\n{graph_text}"

        return context, imgs, chunk_map

    # ------------------------------------------------------------------ #
    #  내부 메서드                                                          #
    # ------------------------------------------------------------------ #

    def _get_graph_context(self, query: str) -> str:
        """
        Graph DB(Neo4j 등) 연동 지점.
        설비 간 계층 구조, 부품 조립 관계 등을 반환합니다.
        """
        # TODO: Neo4j 또는 다른 Graph DB 쿼리 구현
        # 예시:
        # results = self.graph_db.run("MATCH (a)-[r]->(b) WHERE a.name = $q RETURN ...", q=query)
        # return format_graph_results(results)
        return "[Graph DB 미연동 — 관계 정보 없음]"