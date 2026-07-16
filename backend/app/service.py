# backend/app/service.py
import asyncio
import json
import re
from typing import Any
from datetime import datetime
from pathlib import Path

from app.factories.config import Config
from app.core.llm_handler import LLMProvider
from app.core.retriever import (
    BaseRetriever,
    ChromaRetriever,
    FAISSRetriever,
    KGRetriever,
    MultimodalRetriever,
)
from app.core.prompt_manager import PromptManager
from app.core.memory_manager import MemoryManager
from app.core.judge import judge_triple
from app.database import database

INTENT_TYPES = {
    "emergency_action",
    "troubleshooting",
    "part_identification",
    "root_cause_analysis",
    "concept_explanation",
}


class RAGService:
    def __init__(self, config: Config):
        self.config = config
        self.llm = LLMProvider.get_model(config)
        self.memory_manager = MemoryManager()
        self.prompt_manager = PromptManager()
        self._retrievers: dict[str, BaseRetriever] = {}

    def _save_search_result_json(
        self,
        session_id: str,
        payload: dict[str, Any],
        prefix: str = "search",
    ) -> str:
        out_dir = Path("logs") / "search_results"
        out_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = out_dir / f"{prefix}_{session_id}_{ts}.json"

        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        return str(out_path)

    # 단발성 프롬프트 조립용 레거시- memory_manager 사용 X
    async def prepare_context(
        self,
        question: str,
        mode: str,
        prompt_id: str = "tech_expert",   # ✅ main.py에서 전달받도록 추가
        user_prompt: str | None = None,
        persona_type: str = "operator",
    ) -> tuple[list, list, list, list, dict]:

        retriever = self._get_retriever(mode)
        context = ""
        imgs = []
        tables = []
        chunks = []
        
        if retriever:
            context, imgs, tables, chunks = retriever.get_context(question)
        intent = await self._resolve_intent(question, persona_type)

        messages = self.prompt_manager.build(
            prompt_id=prompt_id,          # ✅ main.py의 request.prompt_id 반영
            question=question,
            history=[],                   # ✅ prepare_context에서는 대화 기록 없이 프롬프트만 조립
            context=context,
            mode=mode,
            user_prompt=user_prompt,
            m_info={},
            persona_type=persona_type,
            intent_type=intent["type"],
        )
        return messages, imgs, tables, chunks, intent

    # ask/ask_stream의 공통 준비함수
    # session_id 기준으로 휘발성 memory history를 가져오고, RAG context/user_prompt와 함께 messages를 조립한다.
    async def prepare_ask_context(
        self,
        session_id: str,
        question: str,
        effective_machine_code: str = "ALL",
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        persona_type: str = "operator",
        restore_memory: bool = False,
    ) -> tuple[list, list, list, list, dict]:

        history = self.memory_manager.get_history(session_id)
        intent = await self._resolve_intent(question, persona_type)

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
        m_info = {}

        retriever = self._get_retriever(mode)
        if retriever:
            context, imgs, tables, chunks = retriever.get_context(query=question, machine_code=effective_machine_code)
            m_info = self.config.machines.get(effective_machine_code, {})

        # if mode == "multimodal":
        #     messages = self.prompt_manager.build_multimodal(
        #         question=question,
        #         context=context,
        #         history=history,
        #     )
        # else:
        messages = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history,
            context=context,
            mode=mode,
            user_prompt=user_prompt,
            persona_type=persona_type,
            m_info=m_info,
            intent_type=intent["type"],
        )

        return messages, imgs, tables, chunks, intent
    
    # Chat에서 실제 사용하는 정식 스트리밍 함수
    # metadata를 먼저 보내고, 이후 LLM 토큰을 순차적으로 yield한다.
    # 전체 답변이 끝난 뒤 현재 턴을 MemoryManager에 저장한다.
    async def ask_stream(
        self,
        session_id: str,
        question: str,
        effective_machine_code: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        persona_type: str = "operator",
        restore_memory: bool = False,
    ):
        # prepare_ask_context로 준비물 생성
        # metadata 이벤트 먼저 yield
        # LLM token을 하나씩 yield
        # 마지막에 전체 답변을 memory에 저장

        messages, imgs, tables, chunks, intent = await self.prepare_ask_context(
            session_id=session_id,
            question=question,
            mode=mode,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            persona_type=persona_type,
            restore_memory=restore_memory,
            effective_machine_code=effective_machine_code
        )

        yield {
            "type": "metadata",
            "data": {
                "images": imgs,
                "tables": tables,
                "chunks": chunks,
                "intent": intent,
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

        search_log = {
            "mode": mode,
            "question": question,
            "answer": answer,
            "machine_code": effective_machine_code,
            "context": messages[-1]["content"],
            "images": imgs,
            "tables": tables,
            "chunks": chunks,
        }

        self._save_search_result_json(
            session_id=session_id,
            payload=search_log,
            prefix=mode,
        )

        self.memory_manager.add_turn(session_id, question, answer)

    def _get_retriever(self, mode: str) -> BaseRetriever | None:
        if mode not in self._retrievers:
            if mode in {"rag", "chroma"}:
                self._retrievers[mode] = ChromaRetriever(self.config, use_bm25=True)
            elif mode == "faiss":
                self._retrievers[mode] = FAISSRetriever(self.config, use_bm25=True)
            elif mode == "kg":
                self._retrievers[mode] = KGRetriever(self.config)
            elif mode == "multimodal":
                self._retrievers[mode] = MultimodalRetriever(self.config)
            elif mode == "base":
                return None
            else:
                raise ValueError(f"Unsupported retriever mode: {mode}")
        return self._retrievers[mode]

    async def _resolve_intent(self, question: str, persona_type: str) -> dict:
        rule_intent = self._detect_intent_by_rule(question)
        if rule_intent is not None:
            print(
                "[INTENT] "
                f"type={rule_intent['type']} source=rule confidence=high "
                f"persona={persona_type} matched_rule={rule_intent['matched_rule']}"
            )
            return rule_intent

        llm_intent = await self._classify_intent_with_llm(question, persona_type)
        print(
            "[INTENT] "
            f"type={llm_intent['type']} source={llm_intent['source']} "
            f"confidence={llm_intent['confidence']} persona={persona_type}"
        )
        return llm_intent

    def _detect_intent_by_rule(self, question: str) -> dict | None:
        normalized = question.lower()

        if self._contains_any(normalized, ["반복", "계속", "재발", "패턴", "근본 원인", "원인 분석"]):
            return {
                "type": "root_cause_analysis",
                "source": "rule",
                "confidence": "high",
                "matched_rule": "root_cause_keywords",
            }

        if self._contains_any(normalized, ["부품", "도면", "좌표", "주소", "km", "fr", "qf", "sq", "yv"]) or re.search(r"[xy]\d+", normalized):
            return {
                "type": "part_identification",
                "source": "rule",
                "confidence": "high",
                "matched_rule": "part_or_drawing_keywords",
            }

        if self._contains_any(normalized, ["뜻", "의미", "설명", "개념", "무슨 말", "뭐야"]):
            return {
                "type": "concept_explanation",
                "source": "rule",
                "confidence": "high",
                "matched_rule": "explanation_keywords",
            }

        if self._contains_any(normalized, ["지금", "바로", "먼저", "뭐 해야", "어떻게", "어떻게 해야", "조치", "멈췄", "멈춤", "안돼", "안 돼"]):
            return {
                "type": "emergency_action",
                "source": "rule",
                "confidence": "high",
                "matched_rule": "urgent_action_keywords",
            }

        return None

    async def _classify_intent_with_llm(self, question: str, persona_type: str) -> dict:
        messages = [
            {
                "role": "system",
                "content": (
                    "너는 CNC 정비 Q&A의 intent 분류기다. "
                    "반드시 JSON만 출력한다. "
                    "intent_type은 emergency_action, troubleshooting, part_identification, "
                    "root_cause_analysis, concept_explanation 중 하나다."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"persona_type: {persona_type}\n"
                    f"question: {question}\n"
                    "출력 형식: {\"intent_type\":\"...\",\"confidence\":\"medium\"}"
                ),
            },
        ]

        try:
            raw = await self.llm.ainvoke(messages)
            matched = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(matched.group(0) if matched else raw)
            intent_type = parsed.get("intent_type")
            confidence = parsed.get("confidence", "medium")
            if intent_type in INTENT_TYPES:
                return {
                    "type": intent_type,
                    "source": "llm_classifier",
                    "confidence": confidence,
                    "matched_rule": None,
                }
        except Exception as error:
            return {
                "type": "troubleshooting",
                "source": "fallback",
                "confidence": "low",
                "matched_rule": None,
                "error": error.__class__.__name__,
            }

        return {
            "type": "troubleshooting",
            "source": "fallback",
            "confidence": "low",
            "matched_rule": None,
        }

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    # non-streaming/batch 용도로 남겨둔 후보 함수.
    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        persona_type: str = "operator",
    ) -> dict[str, Any]:
        messages, imgs, tables, chunks, intent = await self.prepare_ask_context(
            session_id=session_id,
            question=question,
            mode=mode,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            persona_type=persona_type,
        )

        answer = await self.llm.ainvoke(messages)

        self.memory_manager.add_turn(session_id, question, answer)
        
        return {
            "answer": answer,
            "metadata": {
                "images": imgs,
                "tables": tables,
                "chunks": chunks,
                "intent": intent,
            },
        }


class JudgeRAGService(RAGService):
    def _is_judge_mode(self, mode: str) -> bool:
        return mode == "judge"

    def _chunks_to_sources(self, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources: list[dict[str, Any]] = []
        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            sources.append({
                "source_doc_name": meta.get("source_doc_name"),
                "section_title": meta.get("section_title"),
                "page_range": meta.get("page_range"),
                "chunk_id": meta.get("chunk_id"),
                "asset_path": meta.get("asset_path"),
                "container_type": meta.get("container_type"),
                "similarity": chunk.get("similarity"),
            })
        return sources

    def _section_titles_from_chunks(self, chunks: list[dict[str, Any]]) -> list[str]:
        titles: list[str] = []
        seen: set[str] = set()

        for chunk in chunks:
            meta = chunk.get("metadata") or {}
            title = str(meta.get("section_title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            titles.append(title)

        return titles

    def _triples_from_chunks(self, chunks: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
        triples: list[tuple[str, str, str]] = []
        for chunk in chunks:
            triple = chunk.get("triple")
            if not triple or len(triple) != 3:
                continue
            triples.append((str(triple[0]), str(triple[1]), str(triple[2])))
        return triples

    async def _answer_branch(
        self,
        question: str,
        mode: str,
        effective_machine_code: str = "ALL",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        history: list | None = None,
    ) -> dict[str, Any]:
        context = ""
        imgs: list[str] = []
        tables: list[str] = []
        chunks: list[dict[str, Any]] = []
        m_info = self.config.machines.get(effective_machine_code, {})

        retriever = self._get_retriever(mode)
        if retriever:
            context, imgs, tables, chunks = retriever.get_context(
                query=question,
                machine_code=effective_machine_code,
            )

        messages = self.prompt_manager.build(
            prompt_id=prompt_id,
            question=question,
            history=history or [],
            context=context,
            mode=mode,
            user_prompt=user_prompt,
            m_info=m_info,
        )

        answer = await self.llm.ainvoke(messages)

        branch_out: dict[str, Any] = {
            "answer": answer,
            "sources": self._chunks_to_sources(chunks),
            "section_titles": self._section_titles_from_chunks(chunks),
            "images": imgs,
            "tables": tables,
            "chunks": chunks,
        }

        if mode == "kg":
            branch_out["triples"] = self._triples_from_chunks(chunks)

        return branch_out

    async def _answer_doc(
        self,
        question: str,
        effective_machine_code: str = "ALL",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        history: list | None = None,
    ) -> dict[str, Any]:
        return await self._answer_branch(
            question=question,
            mode="rag",
            effective_machine_code=effective_machine_code,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            history=history,
        )

    async def _answer_kg(
        self,
        question: str,
        effective_machine_code: str = "ALL",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        history: list | None = None,
    ) -> dict[str, Any]:
        return await self._answer_branch(
            question=question,
            mode="kg",
            effective_machine_code=effective_machine_code,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            history=history,
        )

    async def _answer_multimodal(
        self,
        question: str,
        effective_machine_code: str = "ALL",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        history: list | None = None,
    ) -> dict[str, Any]:
        return await self._answer_branch(
            question=question,
            mode="multimodal",
            effective_machine_code=effective_machine_code,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            history=history,
        )

    def _merge_branch_lists(self, *lists: list[Any]) -> list[Any]:
        merged: list[Any] = []
        seen: set[str] = set()

        for values in lists:
            for value in values or []:
                key = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(value)

        return merged

    async def _answer_with_judge(
        self,
        question: str,
        effective_machine_code: str = "ALL",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        history: list | None = None,
        judge_prompt_id: str = "judge",
    ) -> dict[str, Any]:
        graph_out, doc_out, mm_out = await asyncio.gather(
            self._answer_kg(
                question=question,
                effective_machine_code=effective_machine_code,
                prompt_id=prompt_id,
                user_prompt=user_prompt,
                history=history,
            ),
            self._answer_doc(
                question=question,
                effective_machine_code=effective_machine_code,
                prompt_id=prompt_id,
                user_prompt=user_prompt,
                history=history,
            ),
            self._answer_multimodal(
                question=question,
                effective_machine_code=effective_machine_code,
                prompt_id=prompt_id,
                user_prompt=user_prompt,
                history=history,
            ),
        )

        verdict = await judge_triple(
            llm=self.llm,
            prompt_manager=self.prompt_manager,
            question=question,
            graph_out=graph_out,
            doc_out=doc_out,
            mm_out=mm_out,
            prompt_id=judge_prompt_id,
        )

        branch_map = {
            "A": graph_out,
            "B": doc_out,
            "C": mm_out,
        }
        selected_branch = branch_map.get(verdict.choice)

        if selected_branch is not None:
            images = list(selected_branch.get("images") or [])
            tables = list(selected_branch.get("tables") or [])
            chunks = list(selected_branch.get("chunks") or [])
            section_titles = list(selected_branch.get("section_titles") or [])
            triples = list(selected_branch.get("triples") or [])
        else:
            images = self._merge_branch_lists(
                graph_out.get("images") or [],
                doc_out.get("images") or [],
                mm_out.get("images") or [],
            )
            tables = self._merge_branch_lists(
                graph_out.get("tables") or [],
                doc_out.get("tables") or [],
                mm_out.get("tables") or [],
            )
            chunks = self._merge_branch_lists(
                graph_out.get("chunks") or [],
                doc_out.get("chunks") or [],
                mm_out.get("chunks") or [],
            )
            section_titles = self._merge_branch_lists(
                graph_out.get("section_titles") or [],
                doc_out.get("section_titles") or [],
                mm_out.get("section_titles") or [],
            )
            triples = self._merge_branch_lists(
                graph_out.get("triples") or [],
                doc_out.get("triples") or [],
                mm_out.get("triples") or [],
            )

        judge_log = {
            "mode": "judge",
            "question": question,
            "machine_code": effective_machine_code,
            "judge": {
                "choice": verdict.choice,
                "reason": verdict.reason,
                "final_answer": verdict.final_answer,
                "sources": verdict.sources,
            },
            "branches": {
                "kg": graph_out,
                "rag": doc_out,
                "multimodal": mm_out,
            },
        }

        self._save_search_result_json(
            session_id="",
            payload=judge_log,
            prefix="judge_full",
        )

        return {
            "answer": verdict.final_answer,
            "metadata": {
                "choice": verdict.choice,
                "reason": verdict.reason,
                "sources": verdict.sources,
                "images": images,
                "tables": tables,
                "chunks": chunks,
                "section_titles": section_titles,
                "triples": triples,
                "branches": {
                    "kg": graph_out,
                    "rag": doc_out,
                    "multimodal": mm_out,
                },
            },
        }

    async def ask_stream(
        self,
        session_id: str,
        question: str,
        effective_machine_code: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        restore_memory: bool = False,
    ):
        if not self._is_judge_mode(mode):
            async for event in super().ask_stream(
                session_id=session_id,
                question=question,
                effective_machine_code=effective_machine_code,
                mode=mode,
                prompt_id=prompt_id,
                user_prompt=user_prompt,
                restore_memory=restore_memory,
            ):
                yield event
            return

        history = self.memory_manager.get_history(session_id)

        if restore_memory and not history:
            restored_history = self._load_recent_history_from_db(session_id, question)
            self.memory_manager.set_history(session_id, restored_history)
            await self._compress_memory(session_id, force=True)
            history = self.memory_manager.get_history(session_id)
        else:
            await self._compress_memory(session_id)
            history = self.memory_manager.get_history(session_id)

        result = await self._answer_with_judge(
            question=question,
            effective_machine_code=effective_machine_code,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            history=history,
        )

        yield {
            "type": "metadata",
            "data": result["metadata"],
        }
        yield {
            "type": "token",
            "data": result["answer"],
        }

        self.memory_manager.add_turn(session_id, question, result["answer"])

    async def ask(
        self,
        session_id: str,
        question: str,
        mode: str = "rag",
        prompt_id: str = "tech_expert",
        user_prompt: str | None = None,
        effective_machine_code: str = "ALL",
    ) -> dict[str, Any]:
        if not self._is_judge_mode(mode):
            return await super().ask(
                session_id=session_id,
                question=question,
                mode=mode,
                prompt_id=prompt_id,
                user_prompt=user_prompt,
            )

        history = self.memory_manager.get_history(session_id)
        await self._compress_memory(session_id)
        history = self.memory_manager.get_history(session_id)

        result = await self._answer_with_judge(
            question=question,
            effective_machine_code=effective_machine_code,
            prompt_id=prompt_id,
            user_prompt=user_prompt,
            history=history,
        )
        self.memory_manager.add_turn(session_id, question, result["answer"])
        return result
    
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
