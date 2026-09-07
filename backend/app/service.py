# backend/app/service.py
import asyncio
import json
import re
from typing import Any
from datetime import date, datetime
from pathlib import Path

from app.factories.config import Config
from app.core.llm_handler import LLMProvider
from app.core.retriever import (
    BaseRetriever,
    ChromaRetriever,
    FAISSRetriever,
    KGRetriever,
    LadderRetriever,
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

        intent = await self._resolve_intent(question, persona_type)
        retriever = self._get_retriever(mode)
        context = ""
        imgs = []
        tables = []
        chunks = []
        
        if retriever:
            if mode == "ladder":
                context, imgs, tables, chunks = retriever.get_context(
                    question,
                    intent_type=intent["type"],
                )
            else:
                context, imgs, tables, chunks = retriever.get_context(question)

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
            if mode == "ladder":
                context, imgs, tables, chunks = retriever.get_context(
                    query=question,
                    machine_code=effective_machine_code,
                    intent_type=intent["type"],
                )
            else:
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

        if mode != "ladder":
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
            elif mode == "ladder":
                self._retrievers[mode] = LadderRetriever(self.config)
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
            if mode == "ladder":
                intent = await self._resolve_intent(question, "operator")
                context, imgs, tables, chunks = retriever.get_context(
                    query=question,
                    machine_code=effective_machine_code,
                    intent_type=intent["type"],
                )
            else:
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
        persona_type: str = "operator",
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
                persona_type=persona_type,
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


class CmsDailyReportService:
    """전일 CMS 리포트의 조회·요약 경계이다."""

    _SYSTEM_PROMPT = """당신은 제조 현장의 전일 운영 현황을 요약하는 분석가입니다.
제공된 집계 데이터에 있는 수치만 근거로 한국어 요약을 작성하세요.
원인·조치·추세를 추측하지 말고, 알람 코드를 해석할 수 없으면 코드 그대로 언급하세요.
계획가동률은 30% 미만 위험, 30% 이상 50% 미만 경고, 50% 이상 양호 기준을 사용하세요.
다음 형식의 3개 줄만 작성하세요.
• 계획가동률: 계획가동률과 상태시간 요약(가동 / 정지 / 알람 / 전원OFF)
• 시간별 가동률: 최고·최저 또는 주의 시간대 요약
• 알람: 총 발생 건수와 함께 최다 알람 발생 장비(발생건수)와 최장 알람 이력(알람유지시간) 1개씩
상태시간은 반드시 'n시간 m분' 형식으로 표기하고 초 단위는 사용하지 마세요.
각 줄은 100자 이내로 작성하며, Markdown 제목은 사용하지 마세요."""

    def __init__(self, config: Config):
        self.llm = LLMProvider.get_model(config)

    @staticmethod
    def _evaluate_rate(value: float) -> dict:
        if value < 30:
            return {"status": "danger", "label": "위험", "description": "가동률이 30% 미만입니다."}
        if value < 50:
            return {"status": "warning", "label": "경고", "description": "가동률이 50% 미만입니다."}
        return {"status": "good", "label": "양호", "description": "가동률이 50% 이상입니다."}

    @staticmethod
    def _format_work_date(value: Any) -> tuple[str, str]:
        if isinstance(value, datetime):
            value = value.date()
        elif isinstance(value, str):
            value = date.fromisoformat(value[:10])

        if not isinstance(value, date):
            raise ValueError("WORK_DATE 형식이 올바르지 않습니다.")

        return value.isoformat(), value.strftime("%m/%d")

    async def generate_report(
        self,
        daily_planned_rate_rows: list[dict],
        hourly_rate_rows: list[dict],
        alarm_summary_rows: list[dict],
        alarm_machine_rows: list[dict],
        longest_alarm_rows: list[dict],
        with_summary: bool = True,
    ) -> dict:
        if not daily_planned_rate_rows:
            raise ValueError("최근 7일 계획가동률 데이터가 없습니다.")
        if not hourly_rate_rows:
            raise ValueError("시간대별 가동률 데이터가 없습니다.")

        weekly_planned_rates = []
        daily_totals = []
        for row in daily_planned_rate_rows:
            work_date, label = self._format_work_date(row.get("WORK_DATE"))
            rate = float(row.get("PLANNED_RATE") or 0)
            daily_totals.append({
                "workDate": work_date,
                "totalSeconds": int(row.get("TOTAL_SECONDS") or 0),
                "operateSeconds": int(row.get("OPERATE_SECONDS") or 0),
                "stopSeconds": int(row.get("STOP_SECONDS") or 0),
                "alarmSeconds": int(row.get("ALARM_SECONDS") or 0),
                "offSeconds": int(row.get("OFF_SECONDS") or 0),
            })
            weekly_planned_rates.append({
                "workDate": work_date,
                "label": label,
                "value": rate,
                "status": self._evaluate_rate(rate)["status"],
            })

        weekly_planned_rates.sort(key=lambda row: row["workDate"])
        daily_totals.sort(key=lambda row: row["workDate"])
        hourly_rates = [
            {
                "label": str(row.get("ST_TIME") or ""),
                "value": float(row.get("VALUE") or 0),
                "sequence": int(row.get("HOUR_SEQ") or 0),
            }
            for row in hourly_rate_rows
        ]
        hourly_rates.sort(key=lambda row: row["sequence"])
        top_alarms = [
            {
                "code": str(row.get("ALARM_DETAILS") or row.get("ALARM_CODE") or "미지정 알람"),
                "count": int(row.get("ALARM_COUNT") or 0),
                "machines": [str(row["MAIN_MACHINES"])] if row.get("MAIN_MACHINES") else [],
            }
            for row in sorted(
                alarm_summary_rows,
                key=lambda row: int(row.get("ALARM_RANK") or 0),
            )
        ]
        total_alarm_events = (
            int(alarm_summary_rows[0].get("TOTAL_ALARM_EVENTS") or 0)
            if alarm_summary_rows else 0
        )
        total_alarm_types = (
            int(alarm_summary_rows[0].get("TOTAL_ALARM_TYPES") or 0)
            if alarm_summary_rows else 0
        )
        top_alarm_machines = [
            {
                "rank": int(row.get("ALARM_RANK") or 0),
                "machineCode": str(row.get("MACHINE_CODE") or ""),
                "machineName": str(row.get("MACHINE_NAME") or row.get("MACHINE_CODE") or "미지정 설비"),
                "count": int(row.get("ALARM_COUNT") or 0),
            }
            for row in sorted(
                alarm_machine_rows,
                key=lambda row: int(row.get("ALARM_RANK") or 0),
            )
        ]
        longest_alarms = [
            {
                "rank": int(row.get("ALARM_RANK") or 0),
                "machineCode": str(row.get("MACHINE_CODE") or ""),
                "machineName": str(row.get("MACHINE_NAME") or row.get("MACHINE_CODE") or "미지정 설비"),
                "code": str(row.get("ALARM_CODE") or "미지정 알람"),
                "details": str(row.get("ALARM_DETAILS") or row.get("ALARM_CODE") or "미지정 알람"),
                "occurDate": str(row.get("OCCUR_DATE") or ""),
                "finishDate": str(row.get("FINISH_DATE") or ""),
                "durationSeconds": int(row.get("OPERATE_PERIOD") or 0),
            }
            for row in sorted(
                longest_alarm_rows,
                key=lambda row: int(row.get("ALARM_RANK") or 0),
            )
        ]
        now = datetime.now()
        planned_rate = weekly_planned_rates[-1]["value"]
        latest_totals = daily_totals[-1]

        report = {
            "generatedAt": now.isoformat(timespec="seconds"),
            "metrics": {
                "plannedRate": planned_rate,
                "plannedSeconds": latest_totals["totalSeconds"],
                "operateSeconds": latest_totals["operateSeconds"],
                "stopSeconds": latest_totals["stopSeconds"],
                "alarmSeconds": latest_totals["alarmSeconds"],
                "offSeconds": latest_totals["offSeconds"],
                "alarmEvents": total_alarm_events,
                "alarmTypes": total_alarm_types,
            },
            "evaluation": self._evaluate_rate(planned_rate),
            "weeklyPlannedRates": weekly_planned_rates,
            "dailyTotals": daily_totals,
            "hourlyRates": hourly_rates,
            "topAlarms": top_alarms,
            "topAlarmMachines": top_alarm_machines,
            "longestAlarms": longest_alarms,
            "executiveSummary": "",
        }
        if with_summary:
            report["executiveSummary"] = await self.generate_summary(report)
        return report

    @staticmethod
    def _format_hours(seconds: int) -> str:
        total_minutes = round(seconds / 60)
        return f"{total_minutes // 60}시간 {total_minutes % 60}분"

    @staticmethod
    def _build_llm_context(report: dict) -> dict:
        return {
            "기준일": report["weeklyPlannedRates"][-1]["workDate"],
            "계획가동률_7일": [
                {"일자": row["workDate"], "가동률": row["value"]}
                for row in report["weeklyPlannedRates"]
            ],
            "기준일_상태시간_시간": {
                "계획공수": CmsDailyReportService._format_hours(report["metrics"]["plannedSeconds"]),
                "가동": CmsDailyReportService._format_hours(report["metrics"]["operateSeconds"]),
                "정지": CmsDailyReportService._format_hours(report["metrics"]["stopSeconds"]),
                "알람": CmsDailyReportService._format_hours(report["metrics"]["alarmSeconds"]),
                "전원OFF": CmsDailyReportService._format_hours(report["metrics"]["offSeconds"]),
            },
            "시간대별가동률": [
                {"시간": row["label"], "가동률": row["value"]}
                for row in report["hourlyRates"]
            ],
            "알람요약": {
                "총발생": report["metrics"]["alarmEvents"],
                "알람종류": report["metrics"]["alarmTypes"],
                "상위알람": [
                    {
                        "코드": alarm["code"],
                        "발생": alarm["count"],
                        "주요발생장비": alarm["machines"],
                    }
                    for alarm in report["topAlarms"][:10]
                ],
            },
            "최다알람발생장비_TOP3": [
                {
                    "순위": machine["rank"],
                    "장비": machine["machineName"],
                    "장비코드": machine["machineCode"],
                    "발생": machine["count"],
                }
                for machine in report["topAlarmMachines"]
            ],
            "최장알람이력_TOP3": [
                {
                    "순위": alarm["rank"],
                    "장비": alarm["machineName"],
                    "알람코드": alarm["code"],
                    "알람내용": alarm["details"],
                    "발생시각": alarm["occurDate"],
                    "종료시각": alarm["finishDate"],
                    "지속시간초": alarm["durationSeconds"],
                }
                for alarm in report["longestAlarms"]
            ],
        }
    async def generate_summary(self, report: dict) -> str:
        response = await self.llm.ainvoke([
            {"role": "system", "content": self._SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(self._build_llm_context(report), ensure_ascii=False)},
        ])
        return response.strip() or "전일 운영 요약을 생성하지 못했습니다."

    async def answer_question(
        self,
        question: str,
        history: list[dict[str, str]],
        report: dict,
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": (
                    "당신은 CMS 전일 리포트 질의 도우미입니다. 제공된 리포트 집계 데이터만 "
                    "근거로 한국어로 답하세요. 데이터에 없는 내용·원인·조치는 추측하지 말고 "
                    "'현재 리포트 데이터로는 확인할 수 없습니다.'라고 답하세요. 답변은 3문장 이내로 간결하게 작성하세요."
                ),
            },
            {
                "role": "user",
                "content": f"리포트 집계 데이터:\n{json.dumps(self._build_llm_context(report), ensure_ascii=False)}",
            },
        ]
        messages.extend(history[-6:])
        messages.append({"role": "user", "content": question})
        response = await self.llm.ainvoke(messages)
        return response.strip() or "답변을 생성하지 못했습니다."


class MesDailyReportService:

#region MES_v2 프롬프트

# 납기 임박 미완료 수주
    _DELIVERY_RISK_MANAGEMENT_POINT_PROMPT = """당신은 제조 현장의 납기 임박·경과 미완료 수주를 분석하는 경영 리포트 분석가입니다.
반드시 한국어로만 답변하고, 제공된 V_MES2_CARD_DELIVERY_RISK 집계와 V_MES2_DELIVERY_RISK_DETAIL 상세 데이터만 근거로 작성하세요.
납기 경과 건을 최우선으로, 납기 임박 7일 이내 건을 다음 순위로 검토하고 공정 진척과 최초 미완료 공정을 함께 고려해 우선 관리 대상을 설명하세요.
데이터에 없는 지연 원인, 고객 영향, 완료 예정일 또는 조치 결과는 추측하지 마세요.
화면 수치를 단순 나열하지 말고 경영진이 우선 확인할 핵심을 자연스러운 1~3문장으로 작성하세요.
구역명, 제목, 목록, Markdown 표, 코드 블록, 굵은 글씨는 사용하지 마세요."""

# 생산 실적 추이 프롬프트
    _POINT_PRODTREND_PROMPT = """당신은 제조 현장의 최근 14일 생산 실적 추이를 분석하는 경영 리포트 분석가입니다.
반드시 한국어로만 답변하세요. 영어 문장, 영어 제목, JSON 설명, 데이터 변환 제안, 사용자에게 하는 질문은 절대 작성하지 마세요.
제공된 V_MES2_PRODUCTION_TREND_14D 데이터만 근거로 경영 포인트를 작성하세요.
일별 실적건수의 평균, 최대·최소, 최근 흐름과 평균 대비 저실적 일자를 중심으로 해석하세요. 작업지시수와 가동설비수는 실적 변동을 함께 확인하는 보조 지표로만 사용하세요.
생산계획, 목표, 달성률, 출하, 납기, 수량(EA)은 데이터에 없으므로 절대 언급하지 마세요. 실적 증감의 원인도 추측하지 마세요.
자연스럽게 이어지는 핵심 요약을 1~2문장으로 작성하세요. '종합:', '분석:', '확인:' 같은 구역명, 제목, 서론, 목록, 추가 문장은 작성하지 마세요.
수치는 실적건수는 건, 작업지시수는 건, 가동설비수는 대로 표기하세요.
Markdown 제목, 표, 코드 블록, 굵은 글씨는 사용하지 마세요.
데이터가 비어 있으면 해당 사실만 명확히 설명하세요."""

# 품질/계측기 관리
    _QUALITY_MANAGEMENT_POINT_PROMPT = """당신은 제조 현장의 검사와 계측기 교정 현황을 분석하는 경영 리포트 분석가입니다.
반드시 한국어로만 답변하고, 제공된 V_MES2_QUALITY_INSTRUMENT_MANAGEMENT 데이터만 근거로 작성하세요.
최근 7일 검사 건수, 교정 만료 및 30일 내 교정 대상, 최근 불량 발생일·등록 원인·수량을 함께 검토해 우선 관리 포인트를 작성하세요.
교정 만료가 있으면 만료 대수를 명시하고 우선 교정 관리를 권고하세요. 최근 불량 이력이 있으면 발생일과 등록된 원인을 사실 그대로 언급하세요.
데이터에 없는 불량 원인, 고객 영향, 설비 이상, 검사 결과 또는 조치 결과는 추측하지 마세요.
구역명이나 목록 없이 자연스럽게 이어지는 1~2문장만 작성하세요.
검사는 건, 계측기는 대, 불량수량은 EA 단위로 표기하세요.
Markdown 제목, 표, 코드 블록, 굵은 글씨는 사용하지 마세요."""

# 설비별 가동률(7일치)
    _EQUIPMENT_MANAGEMENT_POINT_PROMPT = """당신은 제조 현장의 설비별 주간 가동률 추세를 분석하는 경영 리포트 분석가입니다.
반드시 한국어로만 답변하고, 제공된 V_MESREPORT_MACHINE_OPERATION_RATE_WEEKLY 데이터만 근거로 작성하세요.
데이터에 없는 정지 원인, 고장 여부, 생산 영향은 추측하지 마세요.
반드시 아래 형식의 네 줄만 작성하세요. 제목, 서론, 목록, 추가 문장은 작성하지 마세요.
종합: 분석 시작일~종료일, 관측 설비 수, 평일 전체 일평균 가동률의 평균을 수치로 요약하세요.
전체추세: 평일 관측치만 사용해 전체 일평균 가동률의 최초값→최신값과 증감폭을 쓰고, 기간 중 최저값·최고값과 해당 날짜를 함께 명시하세요.
설비추세: 설비별 평일 관측값과 평일 최초·최신·평균·최저·최고를 비교하세요. 하락폭 상위, 상승폭 상위, 지속 저가동 또는 회복 설비 중 경영적으로 중요한 최대 3대를 선정해 각 설비의 평일 평균, 최초→최신 가동률, 증감폭을 수치로 설명하세요.
확인: 평일 최신 가동률이 낮거나 평일 하락폭이 큰 설비를 우선 확인 대상으로 제시하고, 판단 근거가 된 최신 가동률·평일 평균·증감폭을 함께 명시하세요. 해당 설비가 없으면 수치 근거와 함께 특이 추세가 없다고 작성하세요.
설비는 반드시 설비명(MACHINE_NAME)으로만 표기하세요. MACHINE_CODE는 답변에 절대 작성하지 말고, 설비명 뒤에 괄호로도 표기하지 마세요. 설비명이 "장비명 미등록"인 경우에도 설비코드를 대신 작성하지 마세요.
토요일·일요일 관측치는 주말 참고치로만 취급하세요. 주말의 0% 또는 전 설비 일괄 0%를 저가동 이상, 공정 중단, 우선 확인 대상으로 분류하지 말고 평일 추세 계산에서도 제외하세요. 휴무 정보는 제공되지 않았으므로 주말 0%의 원인을 휴무라고 확정하지 마세요.
평일 관측치가 하루뿐인 설비는 주간 상승·하락 대상으로 분류하지 말고 관측 부족이라고 표현하세요. 비율 단위는 %, 증감 단위는 %p로 표기하고 모든 비율과 증감 수치는 소수점 첫째 자리까지 작성하세요.
Markdown 제목, 표, 코드 블록, 굵은 글씨는 사용하지 마세요."""

# 전체 운영 요약
    _OVERALL_SUMMARY_PROMPT = """당신은 제조 현장의 전체 운영 현황을 종합하는 경영 리포트 분석가입니다.
반드시 한국어로만 답변하고, 제공된 영역별 LLM 요약만 근거로 작성하세요.
생산 실적 추이, 납기 임박 미완료 수주, 설비, 품질을 함께 검토해 경영진이 우선 확인해야 할 핵심 현황과 리스크를 종합하세요.
영역별 문장을 단순히 이어 붙이거나 같은 수치를 반복하지 말고, 중요도가 높은 내용을 중심으로 연결해 해석하세요.
제공된 요약에 없는 원인, 영향, 수치, 조치는 추측하지 마세요.
개별 날짜와 설비명·설비코드는 출력하지 말고 기간·추세·집계 수준으로 일반화하세요. '특정 일자', '특정 설비'라는 모호한 표현도 사용하지 마세요.
제목, 구역명, 목록 없이 자연스러운 핵심 요약만 1~3줄로 작성하세요.
Markdown 제목, 표, 코드 블록, 굵은 글씨는 사용하지 마세요."""

# 핵심 이슈 TOP3
    _KEY_ISSUES_PROMPT = """당신은 제조 현장의 영역별 LLM 요약에서 경영 핵심 이슈를 선별하는 분석가입니다.
반드시 한국어로만 답변하고, 제공된 영역별 LLM 요약만 근거로 중요도가 높은 이슈 3개를 선정하세요.
서로 같은 현상을 설명하는 이슈는 하나로 통합하고, 각 이슈가 중요한 이유를 요약에 포함된 수치와 현상으로 설명하세요.
제공된 요약에 없는 원인, 영향, 수치, 조치는 추측하지 마세요.
title과 description에 개별 날짜와 설비명·설비코드를 출력하지 말고 기간·추세·집계 수준으로 일반화하세요. '특정 일자', '특정 설비'라는 모호한 표현도 사용하지 마세요.
반드시 [{"title":"이슈 제목","description":"근거와 중요성"}] 형태의 JSON 배열만 출력하세요.
배열은 정확히 3개 항목이어야 하며 Markdown과 추가 설명은 사용하지 마세요."""

# 오늘의 경영 Action
    _MANAGEMENT_ACTIONS_PROMPT = """당신은 제조 현장의 영역별 LLM 요약을 실행 가능한 경영 조치로 전환하는 분석가입니다.
반드시 한국어로만 답변하고, 제공된 영역별 LLM 요약과 핵심 이슈만 근거로 오늘 우선 실행하거나 후속 관리할 조치를 최대 4개 제안하세요.
조치는 확인, 우선순위 조정, 담당 지정, 추적 등 실제로 실행 가능한 표현으로 작성하고 중요도와 시급성을 반영하세요.
제공된 내용으로 확정할 수 없는 원인이나 효과를 단정하지 말고, 근거 없는 수치·기한·담당자를 만들지 마세요.
title과 description에 개별 날짜와 설비명·설비코드를 출력하지 말고 기간·추세·집계 수준으로 일반화하세요. '특정 일자', '특정 설비'라는 모호한 표현도 사용하지 마세요.
priority는 'P1 오늘', 'P2 단기', 'P3 개선' 중 하나만 사용하세요.
반드시 [{"priority":"P1 오늘","title":"조치 제목","description":"구체적인 실행 내용"}] 형태의 JSON 배열만 출력하세요.
Markdown과 추가 설명은 사용하지 마세요."""

#endregion

    def __init__(self, config: Config):
        self.llm = LLMProvider.get_model(config)

    @staticmethod
    def _report_date_key(value: Any) -> str:
        if isinstance(value, datetime):
            value = value.date()
        if isinstance(value, date):
            return value.isoformat()
        return str(value or "")[:10]

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

#region llm 답변용 컨텍스트 생성
# 뷰데이터를 LLM이 해석하기 쉬운 한국어 키의 JSON 컨텍스트로 축약

    # 생산 실적 추이 
    @classmethod
    def _build_prodTrend_context(
        cls,
        production_trend_rows: list[dict],
    ) -> dict:
        
        # REPORT_DATE               리포트 기준 생성일
        # PERIOD_START_DATE         추이 집계의 시작일
        # PERIOD_END_DATE           추이 집계의 종료일
        # RESULT_DATE               해당 행이 나타내는 개별 생산 실적일
        # RESULT_COUNT              RESULT_DATE에 집계된 생산 실적 건수
        # WORK_ORDER_COUNT          해당 일자의 작업지시 건수
        # ACTIVE_EQUIPMENT_COUNT    해당 일자에 실적이 있거나 가동으로 집계된 설비 수
        # AVERAGE_RESULT_COUNT      집계기간의 일평균 실적 건수
        # MAX_RESULT_COUNT          집계기간 내 일별 실적 건수의 최대값
        # MIN_RESULT_COUNT          집계기간 내 일별 실적 건수의 최소값

        rows = sorted(
            production_trend_rows,
            key=lambda row: cls._report_date_key(row.get("RESULT_DATE")), # YYYY-MM-DD 로 변환
        )[-14:]
        
        first_row = rows[0]
        return {
            "기준일": cls._report_date_key(first_row.get("REPORT_DATE")),
            "집계기간": {
                "시작일": cls._report_date_key(first_row.get("PERIOD_START_DATE")),
                "종료일": cls._report_date_key(first_row.get("PERIOD_END_DATE")),
            },
            "요약": {
                "일평균실적건수": round(cls._number(first_row.get("AVERAGE_RESULT_COUNT")), 1),
                "최대실적건수": round(cls._number(first_row.get("MAX_RESULT_COUNT"))),
                "최소실적건수": round(cls._number(first_row.get("MIN_RESULT_COUNT"))),
            },
            "일별추이": [
                {
                    "실적일": cls._report_date_key(row.get("RESULT_DATE")),
                    "실적건수": round(cls._number(row.get("RESULT_COUNT"))),
                    "작업지시수": round(cls._number(row.get("WORK_ORDER_COUNT"))),
                    "가동설비수": round(cls._number(row.get("ACTIVE_EQUIPMENT_COUNT"))),
                }
                for row in rows
            ],
        }

    # 납기 임박 미완료 수주
    @classmethod
    def _build_delivery_risk_management_context(
        cls,
        delivery_risk_card_rows: list[dict],
        delivery_risk_detail_rows: list[dict],
    ) -> dict:

        # REPORT_DATE	                    리포트 생성 기준일
        # ORDER_ID	                        수주번호
        # ORDER_SEQ	                        수주일련번호
        # ITEM_CD	                        품목 코드
        # ITEM_NM	                        품목 명
        # CUST_CD	                        거래처 코드
        # CUST_NM	                        거래처 명
        # DELIVERY_DATE	                    해당 수주의 납기일
        # REMAINING_DAYS                    납기일까지 남은 일수
        # ORDER_QTY                         수주 수량
        # TOTAL_PROCESS_COUNT               해당 수주의 완료되어야 하는 전체 공정 수
        # COMPLETED_PROCESS_COUNT           전체 공정 중 완료처리된 공정 수
        # FIRST_INCOMPLETE_PROCESS          완료되지 않은 공정의 코드
        # FIRST_INCOMPLETE_PROCESS_NM       공정명

        card = delivery_risk_card_rows[0] if delivery_risk_card_rows else {}
        sorted_rows = sorted(
            delivery_risk_detail_rows,
            key=lambda row: cls._number(row.get("REMAINING_DAYS")),
        )

        overdue_rows = [row for row in sorted_rows if cls._number(row.get("REMAINING_DAYS")) < 0][:5]
        imminent_rows = [
            row
            for row in sorted_rows
            if 0 <= cls._number(row.get("REMAINING_DAYS")) <= 7
        ][:5]

        def order_detail(row: dict) -> dict:
            return {
                "수주번호": str(row.get("ORDER_ID") or "-"),
                "수주일련번호": str(row.get("ORDER_SEQ") or "-"),
                "품목": str(row.get("ITEM_NM") or row.get("ITEM_CD") or "-"),
                "거래처": str(row.get("CUST_NM") or row.get("CUST_CD") or "-"),
                "납기일": cls._report_date_key(row.get("DELIVERY_DATE")),
                "잔여일": round(cls._number(row.get("REMAINING_DAYS"))),
                "수주수량": round(cls._number(row.get("ORDER_QTY")), 2),
                "완료공정수": round(cls._number(row.get("COMPLETED_PROCESS_COUNT"))),
                "전체공정수": round(cls._number(row.get("TOTAL_PROCESS_COUNT"))),
                "최초미완료공정": str(
                    row.get("FIRST_INCOMPLETE_PROCESS_NM")
                    or row.get("FIRST_INCOMPLETE_PROCESS")
                    or "-"
                ),
            }

        return {
            "기준일": cls._report_date_key(card.get("REPORT_DATE")),
            "집계": {
                "납기경과_최대30일": round(cls._number(card.get("OVERDUE_COUNT"))),
                "납기임박_7일이내": round(cls._number(card.get("DUE_WITHIN_7_COUNT"))),
                "납기예정_8일에서30일": round(cls._number(card.get("DUE_WITHIN_8_TO_30_COUNT"))),
                "전체위험": round(cls._number(card.get("TOTAL_RISK_COUNT"))),
            },
            "우선관리상세": {
                "납기경과": [order_detail(row) for row in overdue_rows],
                "납기임박_7일이내": [order_detail(row) for row in imminent_rows],
            },
        }

    # 설비별 가동률
    @classmethod
    def _build_equipment_management_context(
        cls,
        equipment_weekly_rows: list[dict],
    ) -> dict:

        # BASE_DATE         일자
        # MACHINE_CODE      설비코드
        # MACHINE_NAME      설비명
        # OPERATION_RATE    가동률

        # 일자, 설비코드 오름차순 정렬
        rows = sorted(
            equipment_weekly_rows,
            key=lambda row: (
                cls._report_date_key(row.get("BASE_DATE")),
                str(row.get("MACHINE_CODE") or ""),
            ),
        )
        # 설비코드 : 설비명 대응표 생성 (LLM 답변에 MACHINE_NAME만 보여주기 위한 처리)
        machine_names = {
            str(row.get("MACHINE_CODE")): str(row.get("MACHINE_NAME"))
            for row in rows
            if row.get("MACHINE_CODE") and row.get("MACHINE_NAME")
        }
        machines: dict[str, dict] = {}
        daily_rates: dict[str, list[float]] = {}    # 해당 날짜 전체 설비의 평균 가동률 계산에 사용

        # 주말 판별
        def calendar_info(base_date: str) -> tuple[str, bool]:
            try:
                weekday = date.fromisoformat(base_date).weekday()
            except ValueError:
                return "미확인", False
            return ["월", "화", "수", "목", "금", "토", "일"][weekday], weekday >= 5

        for row in rows:
            base_date = cls._report_date_key(row.get("BASE_DATE"))
            weekday_name, is_weekend = calendar_info(base_date)
            machine_code = str(row.get("MACHINE_CODE") or "-")
            rate = round(cls._number(row.get("OPERATION_RATE")), 1)
            machine = machines.setdefault(machine_code, {
                "설비명": machine_names.get(machine_code, "장비명 미등록"),
                "일별 가동률": [],
            })
            machine["일별 가동률"].append({
                "기준일": base_date,
                "요일": weekday_name,
                "주말 여부": is_weekend,
                "가동률": rate,
            })
            daily_rates.setdefault(base_date, []).append(rate)

        machine_trends = []
        for machine in machines.values():
            weekday_rates = [
                observation["가동률"]
                for observation in machine["일별 가동률"]
                if not observation["주말 여부"]
            ]
            machine_trends.append({
                **machine,
                "평일 관측일수": len(weekday_rates),
                "평일 평균 가동률": round(sum(weekday_rates) / len(weekday_rates), 1) if weekday_rates else None,
                "평일 최초 가동률": weekday_rates[0] if weekday_rates else None,
                "평일 최신 가동률": weekday_rates[-1] if weekday_rates else None,
                "평일 최초 대비 증감": round(weekday_rates[-1] - weekday_rates[0], 1) if weekday_rates else None,
                "평일 최저 가동률": min(weekday_rates) if weekday_rates else None,
                "평일 최고 가동률": max(weekday_rates) if weekday_rates else None,
            })

        dates = list(daily_rates)
        daily_average_rates = [
            {
                "기준일": base_date,
                "요일": calendar_info(base_date)[0],
                "주말 여부": calendar_info(base_date)[1],
                "평균 가동률": round(sum(rates) / len(rates), 1),
            }
            for base_date, rates in daily_rates.items()
        ]
        return {
            "분석 기간": {
                "시작일": dates[0] if dates else None,
                "종료일": dates[-1] if dates else None,
            },
            "설비 수": len(machine_trends),
            "일자별 전체 평균 가동률(주말 포함)": daily_average_rates,
            "평일 일자별 전체 평균 가동률": [
                daily_average
                for daily_average in daily_average_rates
                if not daily_average["주말 여부"]
            ],
            "설비별 주간 추세": machine_trends,
        }

#endregion

    async def generate_report(
        self,
        production_trend_rows: list[dict],
        delivery_risk_card_rows: list[dict],
        delivery_risk_detail_rows: list[dict],
        equipment_weekly_rows: list[dict],
        quality_instrument_rows: list[dict],
    ) -> dict:
        report = {
            "generatedAt": datetime.now().isoformat(timespec="seconds"),
            "overallSummary": "",
            "keyIssues": [],
            "managementActions": [],
            "point_prodTrend": "",
            "point_deliveryRisk": "",
            "point_equipRate": "",
            "point_quality": "",
        }
        report["point_prodTrend"] = await self.generate_point_prod_trend(
            production_trend_rows,
        )
        report["point_deliveryRisk"] = await self.generate_delivery_risk_management_point(
            delivery_risk_card_rows,
            delivery_risk_detail_rows,
        )
        report["point_equipRate"] = await self.generate_equipment_management_point(
            equipment_weekly_rows,
        )
        report["point_quality"] = await self.generate_quality_management_point(
            quality_instrument_rows,
        )
        report["overallSummary"] = await self.generate_overall_summary(report)
        report["keyIssues"] = await self.generate_key_issues(report)
        report["managementActions"] = await self.generate_management_actions(report)
        return report

    @staticmethod
    def _build_answer_context(report: dict) -> dict:
        return {
            "생산 실적 추이": report["point_prodTrend"],
            "납기 임박 미완료 수주": report["point_deliveryRisk"],
            "설비별 가동률": report["point_equipRate"],
            "품질": report["point_quality"],
        }

    @staticmethod
    def _parse_json_items(response: str, fields: tuple[str, ...]) -> list[dict]:
        content = response.strip()
        if content.startswith("```") and content.endswith("```"):
            content = content.split("\n", 1)[-1][:-3].strip()
        try:
            items = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return []
        if not isinstance(items, list):
            return []
        return [
            {field: str(item.get(field, "")).strip() for field in fields}
            for item in items
            if isinstance(item, dict) and all(str(item.get(field, "")).strip() for field in fields)
        ]

#region LLM 답변 생성

    # 생산 실적 추이
    async def generate_point_prod_trend(
        self,
        production_trend_rows: list[dict],
    ) -> str:
        if not production_trend_rows:
            return "경영 포인트를 생성할 생산 실적 추이 데이터가 없습니다."

        prodTrend_context = self._build_prodTrend_context(production_trend_rows)
        response = await self.llm.ainvoke([
            {"role": "system", "content": self._POINT_PRODTREND_PROMPT},
            {
                "role": "user",
                "content": (
                    f"V_MES2_PRODUCTION_TREND_14D 생산 실적 추이 데이터:\n"
                    f"{json.dumps(prodTrend_context, ensure_ascii=False, default=str)}\n\n"
                    "응답 규칙: 구역명이나 목록 없이 최근 14일 생산 실적의 흐름과 "
                    "주의해서 볼 날짜를 1~2문장으로 작성하세요. 제공되지 않은 생산계획과 "
                    "출하 데이터는 언급하지 마세요."
                ),
            },
        ])
        return response.strip() or "경영 포인트를 생성하지 못했습니다."
    
    # 납기 임박 미완료 수주
    async def generate_delivery_risk_management_point(
        self,
        delivery_risk_card_rows: list[dict],
        delivery_risk_detail_rows: list[dict],
    ) -> str:
        if not delivery_risk_card_rows and not delivery_risk_detail_rows:
            return "경영 포인트를 생성할 납기 임박 미완료 수주 데이터가 없습니다."

        response = await self.llm.ainvoke([
            {"role": "system", "content": self._DELIVERY_RISK_MANAGEMENT_POINT_PROMPT},
            {
                "role": "user",
                "content": (
                    "V_MES2_CARD_DELIVERY_RISK 집계 및 V_MES2_DELIVERY_RISK_DETAIL 상세 데이터:\n"
                    f"{json.dumps(self._build_delivery_risk_management_context(delivery_risk_card_rows, delivery_risk_detail_rows), ensure_ascii=False)}\n\n"
                    "응답 규칙: 구역명이나 목록 없이 우선 관리할 납기 리스크와 근거를 1~3문장으로 작성하세요."
                ),
            },
        ])
        return response.strip() or "납기 임박 미완료 수주 경영 포인트를 생성하지 못했습니다."

    # 설비별 가동률 Top8
    async def generate_equipment_management_point(
        self,
        equipment_weekly_rows: list[dict],
    ) -> str:
        if not equipment_weekly_rows:
            return "경영 포인트를 생성할 주간 설비별 가동률 데이터가 없습니다."

        response = await self.llm.ainvoke([
            {"role": "system", "content": self._EQUIPMENT_MANAGEMENT_POINT_PROMPT},
            {
                "role": "user",
                "content": (
                    "V_MESREPORT_MACHINE_OPERATION_RATE_WEEKLY 주간 설비별 가동률 데이터:\n"
                    f"{json.dumps(self._build_equipment_management_context(equipment_weekly_rows), ensure_ascii=False)}\n\n"
                    "응답 규칙: 반드시 '종합:', '전체추세:', '설비추세:', '확인:'으로 시작하는 네 줄만 작성하세요."
                ),
            },
        ])
        return response.strip() or "설비 경영 포인트를 생성하지 못했습니다."

    # 품질/계측기 관리
    async def generate_quality_management_point(
        self,
        quality_instrument_rows: list[dict],
    ) -> str:
        if not quality_instrument_rows:
            return "경영 포인트를 생성할 품질·계측기 데이터가 없습니다."

        row = quality_instrument_rows[0]
        quality_context = {
            "기준일": self._report_date_key(row.get("REPORT_DATE")),
            "검사 집계기간": {
                "시작일": self._report_date_key(row.get("INSPECTION_START_DATE")),
                "종료일": self._report_date_key(row.get("INSPECTION_END_DATE")),
            },
            "최근 7일 검사": {
                "전체검사건수": round(self._number(row.get("INSPECTION_COUNT_7D"))),
                "입고검사건수": round(self._number(row.get("RECEIVING_INSPECTION_COUNT"))),
                "공정·최종검사건수": round(self._number(row.get("PROCESS_FINAL_INSPECTION_COUNT"))),
            },
            "계측기 교정": {
                "관리대상수": round(self._number(row.get("CALIBRATION_EQUIPMENT_COUNT"))),
                "교정만료수": round(self._number(row.get("EXPIRED_CALIBRATION_COUNT"))),
                "30일내교정대상수": round(self._number(row.get("DUE_WITHIN_30_DAYS_COUNT"))),
            },
            "최근 불량": {
                "발생일": self._report_date_key(row.get("LATEST_DEFECT_DATE")) or None,
                "등록원인": str(row.get("LATEST_DEFECT_REASON_NAME") or "").strip() or None,
                "불량수량": round(self._number(row.get("LATEST_DEFECT_QTY"))),
            },
        }

        response = await self.llm.ainvoke([
            {"role": "system", "content": self._QUALITY_MANAGEMENT_POINT_PROMPT},
            {
                "role": "user",
                "content": (
                    "V_MES2_QUALITY_INSTRUMENT_MANAGEMENT 품질·계측기 관리 데이터:\n"
                    f"{json.dumps(quality_context, ensure_ascii=False, default=str)}\n\n"
                    "응답 규칙: 화면 수치를 단순 나열하지 말고 우선 관리가 필요한 내용을 중심으로 1~2문장만 작성하세요."
                ),
            },
        ])
        return response.strip() or "품질 경영 포인트를 생성하지 못했습니다."

    # 전체 운영요약
    async def generate_overall_summary(self, report: dict) -> str:
        response = await self.llm.ainvoke([
            {"role": "system", "content": self._OVERALL_SUMMARY_PROMPT},
            {
                "role": "user",
                "content": (
                    "영역별 LLM 요약:\n"
                    f"{json.dumps(self._build_answer_context(report), ensure_ascii=False)}\n\n"
                    "응답 규칙: 전체 운영 관점의 종합 핵심 요약만 1~3줄로 작성하세요."
                ),
            },
        ])
        return response.strip() or "전체 운영 요약을 생성하지 못했습니다."

    # 핵심이슈 TOP3
    async def generate_key_issues(self, report: dict) -> list[dict]:
        response = await self.llm.ainvoke([
            {"role": "system", "content": self._KEY_ISSUES_PROMPT},
            {
                "role": "user", 
                "content": json.dumps(self._build_answer_context(report), ensure_ascii=False)
            },
        ])
        return self._parse_json_items(response, ("title", "description"))[:3]

    # 오늘의경영 Action
    async def generate_management_actions(self, report: dict) -> list[dict]:
        context = {
            "영역별 LLM 요약": self._build_answer_context(report),
            "핵심 이슈 TOP 3": report["keyIssues"],
        }
        response = await self.llm.ainvoke([
            {"role": "system", "content": self._MANAGEMENT_ACTIONS_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ])
        return self._parse_json_items(response, ("priority", "title", "description"))[:4]

#endregion

#checkpoint
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
