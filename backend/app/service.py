# backend/app/service.py

from app.factories.config import Config
from app.core.llm_handler import LLMProvider
from app.core.retriever import KnowledgeRetriever
from app.core.prompt_manager import PromptManager
from app.core.memory_manger import MemoryManager


class RAGService:
    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMProvider.get_model(config)
        self.retriever = KnowledgeRetriever(config)
        self.prompt_manager = PromptManager()
        self.memory_manager = MemoryManager()

    # ------------------------------------------------------------------ #
    #  main.py의 chat_endpoint → prepare_context + llm.astream 흐름 지원  #
    # ------------------------------------------------------------------ #

    async def prepare_context(self, question: str, mode: str) -> tuple[str, list, dict]:
        """
        스트리밍 응답 전, 컨텍스트를 미리 구성합니다.
        Returns:
            full_prompt : LLM에 전달할 최종 프롬프트
            imgs        : 관련 이미지 경로 목록
            chunk_map   : 출처 청크 매핑 딕셔너리
        """
        context, imgs, chunk_map = self.retriever.get_context(question, mode)

        full_prompt = self.prompt_manager.build(
            prompt_id=self.config.prompt.prompt_id,
            question=question,
            history="",       # 스트리밍 경로는 히스토리 없이 단발성 처리
            context=context,
            custom_persona=self.config.prompt.system_prompt,
        )
        return full_prompt, imgs, chunk_map

    # ------------------------------------------------------------------ #
    #  일반(비스트리밍) 호출 경로                                           #
    # ------------------------------------------------------------------ #

    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",          # "base" | "rag" | "graph"
        prompt_id: str = "tech_expert",
    ) -> str:
        """
        대화 히스토리를 포함한 단일 응답을 반환합니다.

        mode:
            "base"  — 검색 없이 LLM 상식으로만 답변
            "rag"   — 벡터 DB 검색 결과를 컨텍스트로 활용
            "graph" — 벡터 + 그래프 DB 검색 결과를 컨텍스트로 활용
        """
        # 1. 이전 대화 기록 로드
        history = self.memory_manager.get_history(session_id)

        # 2. 모드별 컨텍스트 확보
        context = ""
        if mode != "base":
            context, _, _ = self.retriever.get_context(question, mode)

        # 3. 프롬프트 조립
        full_prompt = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history,
            context=context,
            custom_persona=self.config.prompt.system_prompt,
        )

        # 4. LLM 호출
        response = await self.llm.ainvoke(full_prompt)
        answer = response.content if hasattr(response, "content") else str(response)

        # 5. 대화 기록 저장
        self.memory_manager.save(session_id, question, answer)

        return answer