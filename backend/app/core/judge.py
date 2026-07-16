from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.core.llm_handler import BaseLLM
from app.core.prompt_manager import PromptManager


@dataclass
class JudgeResult:
    choice: str
    reason: str
    final_answer: str
    sources: list[dict[str, Any]]
    raw: dict[str, Any]


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def _merge_sources(*source_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_list in source_lists:
        for source in source_list or []:
            key = json.dumps(source, ensure_ascii=False, sort_keys=True, default=str)
            if key in seen:
                continue
            seen.add(key)
            merged.append(source)

    return merged


def _sanitize_final_answer(choice: str, final_answer: str, graph_out: dict, doc_out: dict, mm_out: dict) -> str:
    final = (final_answer or "").strip()
    candidates = {
        "A": graph_out.get("answer", "").strip(),
        "B": doc_out.get("answer", "").strip(),
        "C": mm_out.get("answer", "").strip(),
        "SYNTH": graph_out.get("answer", "").strip(),
    }

    if final in {"A", "B", "C", "SYNTH", ""}:
        return candidates.get(choice, candidates["A"])

    return final


def _pick_sources(choice: str, graph_out: dict, doc_out: dict, mm_out: dict) -> list[dict[str, Any]]:
    if choice == "A":
        return list(graph_out.get("sources") or [])
    if choice == "B":
        return list(doc_out.get("sources") or [])
    if choice == "C":
        return list(mm_out.get("sources") or [])
    return _merge_sources(
        graph_out.get("sources") or [],
        doc_out.get("sources") or [],
        mm_out.get("sources") or [],
    )


async def judge_triple(
    llm: BaseLLM,
    prompt_manager: PromptManager,
    question: str,
    graph_out: dict,
    doc_out: dict,
    mm_out: dict,
    prompt_id: str = "judge",
) -> JudgeResult:
    messages = prompt_manager.build_judge_prompt(
        text=question,
        graph_out=graph_out,
        doc_out=doc_out,
        mm_out=mm_out,
        prompt_id=prompt_id,
    )
    raw_text = await llm.ainvoke(messages)
    parsed = _extract_json(raw_text)

    if not parsed:
        return JudgeResult(
            choice="A",
            reason="judge_parse_failed_default_to_graph",
            final_answer=graph_out.get("answer", "").strip(),
            sources=list(graph_out.get("sources") or []),
            raw={"error": "parse_failed", "text": raw_text},
        )

    choice = parsed.get("choice", "A")
    if choice not in {"A", "B", "C", "SYNTH"}:
        choice = "A"

    final_answer = _sanitize_final_answer(
        choice=choice,
        final_answer=parsed.get("final_answer", ""),
        graph_out=graph_out,
        doc_out=doc_out,
        mm_out=mm_out,
    )

    return JudgeResult(
        choice=choice,
        reason=str(parsed.get("reason", ""))[:280],
        final_answer=final_answer,
        sources=_pick_sources(choice, graph_out, doc_out, mm_out),
        raw=parsed,
    )
