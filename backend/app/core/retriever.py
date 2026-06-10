# backend/app/core/retriever.py

import chromadb
from app.factories.config import Config
from app.embeddings import load_embeddings


class KnowledgeRetriever:
    def __init__(self, config: Config):
        self.config = config
        self.chroma = chromadb.PersistentClient(
            path=self.config.vector_db.search_path
        )
        self.embedding_fn = load_embeddings(config=self.config)

        self.collection = self.chroma.get_or_create_collection(
            name=self.config.id,
            embedding_function=self.embedding_fn,
        )

    def get_context(self, query: str, mode: str, machine_code: str) -> tuple[str, list, list, list]:
        """Build retrieval context and metadata for LLM + UI."""
        if mode == "base":
            return "", [], [], []

        if machine_code == "ALL":
            results = self.collection.query(
                query_texts=[query],
                n_results=self.config.vector_db.retrieval_k,
                include=["documents", "metadatas", "distances"],
            )
        else:
            results = self.collection.query(
                query_texts=[query],
                n_results=self.config.vector_db.retrieval_k,
                include=["documents", "metadatas", "distances"],
                where={"machine_code": {"$contains": machine_code.strip()}}
            )

        context_parts: list[str] = []
        chunks: list[dict] = []
        imgs: list[str] = []
        tables: list[str] = []

        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]

        for index, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances), start=1):
            source = meta.get("source_doc_name", "unknown")
            container_type = meta.get("container_type")
            similarity = (1 - float(dist)) if dist is not None else None

            context_parts.append(f"[chunk:{index}]\n[문서: {source}]\n{doc}")

            # Keep chunk metadata rich so frontend can render citations/assets precisely.
            chunks.append({
                "index": index,
                "retrieval_rank": index,
                "document": doc,
                "metadata": meta,
                "distance": float(dist) if dist is not None else None,
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
