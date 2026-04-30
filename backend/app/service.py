# backend/app/service.py
import json
import re
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

    async def prepare_ask_context(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
    ) -> tuple[list, list, list, list]:
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

    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
    ) -> str:
        # 1. 이전 대화 기록 로드 (list 반환)
        history = self.memory_manager.get_history(session_id)

        # 2. 모드별 컨텍스트
        context = ""
        if mode != "base":
            context, _, _, _ = self.retriever.get_context(question, mode)

        # 3. 프롬프트 조립 → messages list
        messages = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history,           
            context=context,
            mode=mode,
            user_prompt=user_prompt,
        )
        # 4. LLM에 메시지 전달 후 답변 수신
        answer_parts = []
        async for token in self.llm.astream(messages):
            answer_parts.append(token)
        answer = "".join(answer_parts)

        # 5. 대화 기록 저장
        # self.memory_manager.add_user_message(session_id, question)
        # self.memory_manager.add_ai_message(session_id, answer)
        self.memory_manager.add_turn(session_id, question, answer)

        return answer
    
class DailyReportService:
    """MES 데일리 리포트 Chain 생성 서비스"""

    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMProvider.get_model(config)
        self.prompt_manager = PromptManager()
        self._system_prompt: str = self.prompt_manager.registry["mes_daily_report"]["persona"]

    # ── 섹션 단위 LLM 호출 ────────────────────────────────────────────────────

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
        parts: list[str] = []
        async for token in self.llm.astream(messages):
            parts.append(token)
        return "".join(parts)

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
