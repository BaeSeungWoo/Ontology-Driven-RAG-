# backend/app/service.py
import json
import re
from app.factories.config import Config
from app.core.llm_handler import LLMProvider
from app.core.retriever import KnowledgeRetriever
from app.core.prompt_manager import PromptManager
from app.core.memory_manager import MemoryManager
from app.database import database


class RAGService:
    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMProvider.get_model(config)
        self.retriever = KnowledgeRetriever(config)
        self.prompt_manager = PromptManager()
        self.memory_manager = MemoryManager()

    # 단발성 프롬프트 조립용 레거시- memory_manager 사용 X
    async def prepare_context(
        self,
        question: str,
        mode: str,
        prompt_id: str = "tech_expert",   # ✅ main.py에서 전달받도록 추가
        user_prompt: str | None = None,
    ) -> tuple[list, list, list, list]:

        context, imgs, tables, chunks = self.retriever.get_context(question, mode)

        messages = self.prompt_manager.build(
            prompt_id=prompt_id,          # ✅ main.py의 request.prompt_id 반영
            question=question,
            history=[],                   # ✅ prepare_context에서는 대화 기록 없이 프롬프트만 조립
            context=context,
            mode=mode,
            user_prompt=user_prompt,
        )
        return messages, imgs, tables, chunks

    # ask/ask_stream의 공통 준비함수
    # session_id 기준으로 휘발성 memory history를 가져오고, RAG context/user_prompt와 함께 messages를 조립한다.
    async def prepare_ask_context(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        restore_memory: bool = False,
    ) -> tuple[list, list, list, list]:
        history = self.memory_manager.get_history(session_id)

        if restore_memory and not history:
            restored_history = self._load_recent_history_from_db(session_id, question)
            self.memory_manager.set_history(session_id, restored_history)
            await self._compress_memory(session_id, force=True)
            history = self.memory_manager.get_history(session_id)
        else:
            await self._compress_memory(session_id)
            history = self.memory_manager.get_history(session_id)

        context = ""
        imgs = []
        tables = []
        chunks = []

        if mode != "base":
            context, imgs, tables, chunks = self.retriever.get_context(question, mode)

        messages = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history,
            context=context,
            mode=mode,
            user_prompt=user_prompt,
        )

        return messages, imgs, tables, chunks
    
    # Chat에서 실제 사용하는 정식 스트리밍 함수
    # metadata를 먼저 보내고, 이후 LLM 토큰을 순차적으로 yield한다.
    # 전체 답변이 끝난 뒤 현재 턴을 MemoryManager에 저장한다.
    async def ask_stream(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        restore_memory: bool = False
    ):
        # prepare_ask_context로 준비물 생성
        # metadata 이벤트 먼저 yield
        # LLM token을 하나씩 yield
        # 마지막에 전체 답변을 memory에 저장

        messages, imgs, tables, chunks = await self.prepare_ask_context(
            session_id=session_id,
            question=question,
            mode=mode,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            restore_memory=restore_memory,
        )

        yield {
            "type": "metadata",
            "data": {
                "images": imgs,
                "tables": tables,
                "chunks": chunks,
            },
        }

        answer_parts = []

        async for token in self.llm.astream(messages):
            answer_parts.append(token)
            yield {
                "type": "token",
                "data": token,
            }

        answer = "".join(answer_parts)
        self.memory_manager.add_turn(session_id, question, answer)

    # non-streaming/batch 용도로 남겨둔 후보 함수.
    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
    ) -> str:
        messages, imgs, tables, chunks = await self.prepare_ask_context(
            session_id=session_id,
            question=question,
            mode=mode,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
        )

        answer = await self.llm.ainvoke(messages)

        self.memory_manager.add_turn(session_id, question, answer)
        
        return {
            "answer": answer,
            "metadata": {
                "images": imgs,
                "tables": tables,
                "chunks": chunks,
            },
        }
    
    def _load_recent_history_from_db(self, session_id: str, current_question: str) -> list:
        rows = database.getChatMessagesBySession(int(session_id))

        messages = []
        for row in rows:
            role = row[2]
            content = row[3]

            if role not in ("user", "assistant"):
                continue
            if not content:
                continue

            messages.append({"role": role, "content": content})

        # 프론트가 /chat 호출 전에 현재 user message를 DB에 먼저 저장하므로,
        # 마지막 user가 현재 질문이면 메모리 복원 대상에서 제외한다.
        if messages and messages[-1]["role"] == "user" and messages[-1]["content"] == current_question:
            messages.pop()

        max_messages = self.memory_manager.window_turns * 2
        return messages[-max_messages:]

    async def _compress_memory(self, session_id: str, force: bool = False):
        history = self.memory_manager.get_history(session_id)
        if not history:
            return
        if not force and not self.memory_manager.should_summarize(session_id):
            return

        summary = await self._summarize_history(session_id, history)
        if not summary:
            return

        self.memory_manager.replace_with_summary(session_id, summary)

    async def _summarize_history(self, session_id: str, history: list) -> str:
        history_text = self._format_history_for_summary(history)
        if not history_text:
            return ""

        messages = self.prompt_manager.build_summary(
            prompt_id="memory_summary",
            history_text=history_text,
        )

        try:
            return (await self.llm.ainvoke(messages)).strip()
        except Exception as e:
            # 요약 실패가 실제 답변 흐름을 막지 않도록 기존 메모리를 그대로 사용한다.
            print(f"memory summary error: session_id={session_id}, error={e}")
            return ""

    def _format_history_for_summary(self, history: list) -> str:
        lines = []
        for message in history:
            role = message.get("role")
            content = message.get("content")

            if role not in ("user", "assistant"):
                continue
            if not content:
                continue

            label = "사용자" if role == "user" else "답변"
            lines.append(f"{label}: {content}")

        return "\n\n".join(lines)

class DailyReportService:
    """MES 데일리 리포트 Chain 생성 서비스"""

    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMProvider.get_model(config)
        self.prompt_manager = PromptManager()
        self._system_prompt: str = self.prompt_manager.registry["mes_daily_report"]["persona"]

    # ── 섹션 단위 LLM 호출 ────────────────────────────────────────────────────

    # 리포트 섹션 생성은 채팅처럼 토큰 스트리밍이 필요 없으므로 ainvoke로 한 번에 생성한다.
    async def _generate_section(self, section: str, section_data: dict | list | str) -> str:
        data_str = (
            section_data
            if isinstance(section_data, str)
            else json.dumps(section_data, ensure_ascii=False, indent=2)
        )
        prompt_text = _SECTION_PROMPTS[section].format(data=data_str)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user",   "content": prompt_text},
        ]

        return await self.llm.ainvoke(messages)

    # ── 출력 검증 ─────────────────────────────────────────────────────────────

    def _validate_output(self, text: str) -> dict:
        sections_ok = bool(re.search(r"^## \d+\.", text, re.MULTILINE))
        json_match  = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        trailing_json: dict | None = None
        if json_match:
            try:
                trailing_json = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        return {"sections_ok": sections_ok, "trailing_json": trailing_json}

    # ── 스트리밍 메인 진입점 ──────────────────────────────────────────────────

    async def astream_report(self, report_date: str, factory: str = "OBI"):
        """섹션별 Chain 호출로 데일리 리포트를 생성하며 토큰을 스트림한다."""
        input_json = self._transform_db_data(report, report_date, factory)

        sections_text: dict[str, str] = {}
        for sec in _SECTION_ORDER:
            data_key = _SECTION_DATA_KEY[sec]
            section_result = await self._generate_section(sec, input_json.get(data_key, {}))
            sections_text[sec] = section_result
            yield section_result
            yield "\n\n"

        # 종합 이슈: 전 섹션 텍스트를 합쳐 전달
        combined = "\n\n".join(sections_text.values())
        summary = await self._generate_section("summary", combined)
        yield summary

    # ── 전체 텍스트 반환 (non-streaming) ─────────────────────────────────────

    async def generate_report(self, report_date: str, factory: str = "OBI") -> str:
        parts: list[str] = []
        async for token in self.astream_report(report_date, factory):
            parts.append(token)
        return "".join(parts)
    
_SECTION_PROMPTS: dict[str, str] = {
     "base": """\
        [GOAL]   
        주어진 데이터를 기반으로 한 문장으로 요약하라.

        [INPUT DATA]
        {data}

        [IMPORTANT RULE]
        -납기를 배송으로 읽지마라.

        [INSTRUCTION]
        - 전체 데이터를 종합적으로 분석하라
        - 유사한 문제는 하나로 묶어라
        - 수치 기반으로 설명하라 (추측 금지)
        - 출력형식은 txt로만, MD형식 금지
    """,

    "compare": """\
        [GOAL]
        주어진 데이터를 기반으로 "기준 데이터를 기반으로 전일 데이터와의 비교"를 한문장으로 요약하라.

        [CRITERIA]
        1. "current"(현재) 데이터를 "previous"(과거) 의 차이(증감, 원인, 리스크 등)
        2. 반드시 수치 비교

        [INPUT DATA]
        1. current: 기준 데이터
        2. previous: 전일 데이터
        {data}

        [IMPORTANT RULE]
        - 반드시 current의 수치를 기준으로 판단하라.
        - current와 previous의 같은 컬럼에 대해서만 비교하라.

        [INSTRUCTION]
        - 유사한 문제는 하나로 묶어라
        - 수치 기반으로 설명하라 (추측 금지)
        - 출력형식은 txt로만, MD형식 금지
    """,

    "issue": """
        [GOAL]
        주어진 데이터를 기반으로 "심각도가 높은 핵심 이슈 TOP 3"를 도출하라.

        [CRITERIA]
        심각도는 아래 기준을 종합적으로 고려하여 판단한다:
        1. 수치 이상 (급격한 증가/감소, 기준 초과)
        2. 비율 이상 (불량률, 부하율 등)
        3. 목표 대비 편차
        4. 시간 흐름 상 악화 추세
        5. 비즈니스 영향도 (생산 차질, 품질 문제 등)
        
        [INPUT DATA]
        1. base: 전체 원본 데이터
        2. summary: 섹션별 요약 코멘트 추가
        {data}

        [IMPORTANT RULE]
        - 반드시 base의 수치를 기준으로 판단하라
        - summary의 Comment는 참고만 하되, 그대로 따르지 마라

        [INSTRUCTION]
        - 전체 데이터를 종합적으로 분석하라
        - 유사한 문제는 하나로 묶어라
        - 반드시 "가장 중요한 3개만" 선택하라
        - 각 이슈는 "왜 문제인지" 근거를 포함해야 한다
        - 수치 기반으로 설명하라 (추측 금지)
        - 서론 같은 거 없이 이슈에 대해서만 설명하라
        - 출력형식은 txt로만, MD형식 금지
        - 번호. 이슈 \n 설명 \n 근거 형식으로 출력
    """
    
}
