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

    async def prepare_context(
        self,
        question: str,
        mode: str,
        prompt_id: str = "tech_expert",   # ✅ main.py에서 전달받도록 추가
    ) -> tuple[list, list, dict]:         

        context, imgs, chunk_map = self.retriever.get_context(question, mode)

        messages = self.prompt_manager.build(
            prompt_id=prompt_id,          # ✅ main.py의 request.prompt_id 반영
            question=question,
            history=[],                   # ✅ prepare_context에서는 대화 기록 없이 프롬프트만 조립
            context=context,
            custom_persona=self.config.prompt.fallback_system_prompt,
        )
        return messages, imgs, chunk_map  

    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
    ) -> str:
        # 1. 이전 대화 기록 로드 (list 반환)
        history = self.memory_manager.get_history(session_id)

        # 2. 모드별 컨텍스트
        context = ""
        if mode != "base":
            context, _, _ = self.retriever.get_context(question, mode)

        # 3. 프롬프트 조립 → messages list
        messages = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history,           
            context=context,
            custom_persona=self.config.prompt.fallback_system_prompt,
        )
        # 4. LLM에 메시지 전달 후 답변 수신
        answer_parts = []
        async for token in self.llm.astream(messages):
            answer_parts.append(token)
        answer = "".join(answer_parts)

        # 5. 대화 기록 저장
        self.memory_manager.add_user_message(session_id, question)
        self.memory_manager.add_ai_message(session_id, answer)

        return answer