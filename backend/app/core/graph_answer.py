"""Compose graph answers from claims whose operating conditions fit the question."""
import json
import re

from pydantic import BaseModel, Field

from app.core.graph_model import graph_completion
from app.core.prompt_manager import ANSWER_SNIPPET_SELECTION


class Condition(BaseModel):
    label: str = Field(min_length=1)
    question_quote: str


class Evidence(BaseModel):
    source: int
    evidence_quote: str = Field(min_length=1)


class Claim(BaseModel):
    sentence: str = Field(min_length=1)
    evidence: list[Evidence]
    conditions: list[Condition]


class GroundedAnswer(BaseModel):
    first_check: str
    check_evidence: list[Evidence]
    claims: list[Claim]


class ManualLine(BaseModel):
    source: int
    quote: str = Field(min_length=3)


class DiagnosticAnswer(BaseModel):
    manual_examples: list[ManualLine]
    first_check: str


def format_diagnostic(plan, sources):
    originals = {s["index"]: s["excerpt"].splitlines() for s in sources}
    examples = {}
    for item in plan.manual_examples:
        lines = originals.get(item.source, [])
        quote = item.quote.strip()
        if quote and any(quote in line for line in lines):
            examples.setdefault((item.source, quote), f"“{quote}” [근거 {item.source}]")
    if not examples:
        return "제공된 매뉴얼 근거만으로 현재 조건에 맞는 조치를 확인할 수 없습니다."
    answer = _card("SUMMARY", "매뉴얼에 나온 관련 조건", "\n".join(examples.values()))
    if plan.first_check.strip():
        answer += "\n\n" + _card("ACTION", "현장에서 확인할 사항", plan.first_check.strip())
    return answer


def _card(kind, title, body):
    return f"> [!{kind}] {title}\n" + "\n".join("> " + line for line in body.splitlines())


def format_answer(plan, question, sources):
    excerpts = {s["index"]: " ".join(s["excerpt"].split()) for s in sources}
    tables = {s["index"]: s["excerpt"].splitlines() for s in sources if s.get("kind") == "table"}
    checks = {}
    lines = []
    for claim in plan.claims:
        if not claim.evidence or any(not e.evidence_quote.strip() or " ".join(e.evidence_quote.split())
                                     not in excerpts.get(e.source, "") for e in claim.evidence):
            continue
        missing = [c.label for c in claim.conditions
                   if not c.question_quote.strip() or c.question_quote not in question]
        table_example = bool(plan.first_check.strip()) and all(e.source in tables for e in claim.evidence)
        if missing and not table_example:
            checks.update(dict.fromkeys(missing))
            continue
        context = ", ".join(c.label for c in claim.conditions)
        prefix = f"({context}) " if context else ""
        refs = "".join(f"[근거 {i}]" for i in dict.fromkeys(e.source for e in claim.evidence))
        if any(e.source in tables for e in claim.evidence):
            # Render the original row, so generated prose cannot reassign its conditions or actions.
            for e in claim.evidence:
                quote = " ".join(e.evidence_quote.split())
                matches = [row.strip() for row in tables.get(e.source, []) if "|" in row
                           and quote in " ".join(row.split())]
                if len(matches) == 1:
                    line = f"매뉴얼 표의 해당 행은 “{matches[0]}”입니다. [근거 {e.source}]"
                    if table_example:
                        line = f"{prefix}매뉴얼의 상태별 예시 — {matches[0]} [근거 {e.source}]"
                    if line not in lines:
                        lines.append(line)
            continue
        lines.append(f"{prefix}{claim.sentence.strip()} {refs}")
    check_text = ""
    if plan.first_check.strip():
        if not lines:
            # A two-state indicator table can supply a worked example even without a confirmed state.
            for source, rows in tables.items():
                if len(rows) != 3:
                    continue
                cells = [[cell.strip() for cell in row.split("|")] for row in rows[1:]]
                if ([row[0].upper() for row in cells] != ["ON", "OFF"]
                        or not all(len(row) >= 3 and "램프" in row[-1] for row in cells)):
                    continue
                words = re.findall(r"[가-힣A-Za-z]{3,}", cells[0][1])
                if any(word in question for word in words):
                    lines.extend(f"상태 표시 예시 — {row[0]} · {row[-1]} · {row[1].lstrip('- ')} [근거 {source}]" for row in cells)
                    break
        verified = []
        for e in plan.check_evidence:
            quote = " ".join(e.evidence_quote.split())
            if quote and quote in excerpts.get(e.source, "") and (
                    e.source not in tables or any(quote in " ".join(row.split()) for row in tables[e.source])):
                verified.append(e.source)
        refs = "".join(f" [근거 {i}]" for i in dict.fromkeys(verified))
        check = plan.first_check.strip()
        identifiers = re.findall(r"(?<![\w])(?:[A-Za-z]+[-.]?)?\d+(?:\.\d+)?", check)
        support = " ".join([question, *(excerpts[i] for i in verified)])
        if any(not re.search(r"(?<![A-Za-z0-9])" + re.escape(code) + r"(?![A-Za-z0-9])",
                             support, re.I) for code in identifiers):
            check = "먼저 증상이 발생한 위치와 당시 선택 상태, 화면에 표시된 알람을 확인해 주세요."
            refs = ""
            for e in plan.check_evidence:
                if e.source in verified and e.source not in tables and e.evidence_quote.strip() in excerpts[e.source]:
                    lines.append(f"매뉴얼의 관련 항목은 “{e.evidence_quote.strip()}”입니다. [근거 {e.source}]")
                    break
        check_text = check + refs
    elif checks:
        check_text = "먼저 다음 사항을 확인해 주세요. " + " · ".join(checks)
    if not lines and not check_text:
        return "제공된 매뉴얼 근거만으로 현재 조건에 맞는 조치를 확인할 수 없습니다."
    sections = []
    if lines:
        sections.append(_card("SUMMARY", "매뉴얼에서 확인한 내용", "\n".join(lines)))
    if check_text:
        sections.append(_card("ACTION", "현장에서 확인할 사항", check_text))
    return "\n\n".join(sections)


# Named modes explicitly stated in manual text, independent of machine or symptom.
_MODE = re.compile(r"(?<![A-Za-z0-9])([A-Z][A-Z0-9_-]{1,20})\s*(?:모드|(?i:mode)\b)")


def mode_context(question, sources):
    modes = {m.group(1) for source in sources for m in _MODE.finditer(source["excerpt"])}
    for mode in sorted(modes):
        # A mention, negation, or hypothetical is insufficient for an operating-state assertion.
        active = re.search(r"(?<![a-z0-9])" + re.escape(mode) +
                           r"\s*(?:모드(?:로|에서|인 상태에서)|mode (?:is )?(?:active|enabled))", question, re.I)
        if active and not re.search(r"아니|아닌|않|꺼|해제|인지|라면|가정|\bif\b|disabled|not ", question, re.I):
            return mode, modes
    return None, modes


def listed_mode_action(sources, mode, symptom):
    for source in sources:
        action = None
        for line in source["excerpt"].splitlines():
            line = line.strip()
            if not line:
                continue
            if not line.startswith("-"):
                heading = re.fullmatch(r"(?:[①-⑳]\s*)?(?:아래|다음)의?\s*경우에(?:는)?\s+(.+[.!?])", line)
                action = heading.group(1) if heading else None
                continue
            condition = line[1:].strip()
            if (action and mode in _MODE.findall(condition) and symptom in condition
                    and condition.endswith("경우")):
                return (f"매뉴얼은 “{condition}”에 해당할 때의 조치를 "
                        f"“{action}”라고 안내합니다. [근거 {source['index']}]")


async def grounded_graph_answer(config, question, sources, instructions, *, symptom=None, alarm=None, targets=None):
    if alarm and sources and all(s.get("kind") == "table" for s in sources):
        rows = []
        code = re.compile(r"(?<![\w#])" + re.escape(alarm) + r"(?!\w)", re.I)
        for source in sources:
            for line in source["excerpt"].splitlines():
                cells = [cell.strip() for cell in line.split("|")]
                if not any(code.search(cell) for cell in cells):
                    continue
                description = " · ".join(cell for cell in cells if len(cell) > len(alarm) and
                                         not re.fullmatch(r"[A-Z]?[0-9.]+", cell))
                if description:
                    rows.append(f"매뉴얼의 {alarm} 항목에는 “{description}”라고 적혀 있습니다. [근거 {source['index']}]")
        if rows:
            return _card("SUMMARY", "매뉴얼의 알람 설명", "\n".join(rows))
    active_mode, source_modes = mode_context(question, sources)
    diagnostic = bool(symptom and not alarm)
    alarm_reported = bool(re.search(r"(?:알람|경보)(?:이|은|은요)?\s*(?:없|안 뜨|미발생)|no alarms?", question, re.I))
    alarm_check = "" if alarm_reported else "표시된 알람이 있는지, 있다면 번호와 메시지를 확인해 주세요."
    if diagnostic and source_modes and not active_mode:
        example = next(s for s in sources if _MODE.search(s["excerpt"]))
        mode = _MODE.search(example["excerpt"]).group(1)
        summary = f"검색된 매뉴얼에는 {mode} 모드에 해당하는 내용이 있습니다. 현재 운전에 적용되는지는 확인이 필요합니다. [근거 {example['index']}]"
        check = f"먼저 증상이 발생했을 때의 실제 운전 모드를 확인해 주세요. {alarm_check}".strip()
        return _card("SUMMARY", "매뉴얼의 적용 조건", summary) + "\n\n" + _card("ACTION", "현장에서 확인할 사항", check)

    if diagnostic and active_mode:
        sources = [s for s in sources if active_mode in _MODE.findall(s["excerpt"])]
        action = listed_mode_action(sources, active_mode, symptom)
        if action:
            return _card("ACTION", "매뉴얼에 명시된 조치", action)

    prompt = (
        "사용자의 질문 사실과 문서 적용 조건을 비교한 뒤 JSON만 반환하세요. "
        "claims에는 핵심 설명을, first_check에는 필요한 현장 확인 사항을 담으세요. "
        "중요한 화면명·부품명은 설명 문장에서 **굵게** 표시할 수 있습니다. 인용 원문은 그대로 복사하세요. "
        "카드 제목과 인용 번호는 서버가 붙이므로 직접 쓰지 마세요. "
        "형식은 {first_check:현장에서 스스로 확인할 사항 또는 빈 문자열,check_evidence:확인할 항목의 명칭과 표시 의미가 나온 근거 배열(source와 evidence_quote),claims:[{sentence:한국어 설명 한 문장,evidence:[{source:근거 번호,"
        "evidence_quote:그 문장을 뒷받침하는 발췌문의 짧고 정확한 연속 원문}],"
        "conditions:[{label:필요한 조건,question_quote:그 조건이 성립함을 밝힌 질문 원문}]}]} 입니다. "
        "검색된 문서의 모드·알람·옵션·작업 단계가 현장에도 해당한다고 추정하지 마세요. "
        "이 화면은 단일 답변입니다. 증상만으로 원인이나 조치를 특정할 수 없으면 first_check에 "
        "적용 대상을 가르는 관찰 항목(어느 위치나 기능에서 발생하는지, 선택 표시, 표시된 알람 등)을 "
        "사용자가 현장에서 눈으로 확인할 문장으로 먼저 쓰세요. first_check에는 분기 판단에 필요한 위치와 상태 표시만 쓰고 "
        "답글 요청, 명령 코드 예시, 프로그램 검사, 버튼 조작·설정 변경은 넣지 마세요. "
        "세부 위치가 생략되어도 매뉴얼에서 질문과 직접 관련된 조작반 표시나 기능 예시를 필요한 만큼 골라 claims에 담으세요. "
        "상태표가 있다면 같은 표의 서로 다른 상태를 각각 한 문장으로, evidence_quote에는 해당 행 전체를 복사하세요. "
        "이를 실제 고장 원인이나 특정 위치의 확정 진단으로 표현하지 마세요. 동일한 조건이 반복되면 중복 설명은 생략하세요. "
        "절차 표는 필요한 행을 각각 인용하고 다른 행이나 표의 조건을 결합하지 마세요. "
        "충분히 특정되거나 진단 질문이 아니면 first_check는 빈 문자열입니다. "
        "모든 조건을 문장마다 독립적으로 평가하세요. 질문에서 조건이 긍정적으로 확인된 경우만 "
        "question_quote에 그대로 복사하세요. 부정·가정·모름·단순 증상 일치는 증명이 아닙니다. "
        "미확인 조건은 label에 쓰고 question_quote는 비우세요. label에는 실제 매뉴얼의 적용 조건만 쓰고 근거 있음 같은 평가 표현은 쓰지 마세요. "
        "원인을 묻는 이상 증상 질문은 먼저 당시 운전 모드와 표시 알람을 파악하세요. 이미 밝힌 모드나 "
        "알람을 다시 묻지 마세요. 특정 알람이 검색됐다는 이유로 그 알람을 일일이 나열하지 마세요. "
        "설명·정의·일반 안전수칙에 불필요한 확인을 붙이지 마세요. 무관한 설치/보수 자료는 제외하세요. "
        "질문에 제시된 알람의 의미를 답할 때 표에 적힌 메시지나 조치를 그대로 설명하고, 적혀 있지 않은 고장이나 원인을 추가하지 마세요. 확인된 조건 안에서도 작업자에게 제어 게인, 파라미터 조정 등을 지시하지 마세요. "
        "질문을 설명하는 데 필요한 만큼 작성하고, 서로 다른 조건에는 각각 직접 근거를 붙이세요. 매뉴얼에서 하나의 조치 아래에 대안 조건들이 열거되어 있으면 질문과 맞는 항목과 상위 조치 문구를 각각 evidence_quote로 인용하세요. 다른 항목을 추가 전제나 확인 사항으로 제시하지 마세요. 질문의 모드와 증상이 해당 항목을 충족하면 그 조건에서 매뉴얼이 명시한 조치를 정확히 보고하세요. 원문에 없는 조정량이나 절차를 만들지 마세요. 매뉴얼이 요구하지 않는 알람 확인을 추가하지 마세요. "
        "직접 인용이 없거나 조건이 불분명하면 claims는 비워도 됩니다. "
        "근거 표시는 서버가 작성하므로 sentence에 인용 번호는 쓰지 마세요."
    )
    schema = GroundedAnswer
    model_sources = sources
    if diagnostic and not active_mode:
        schema = DiagnosticAnswer
        from app.core.controller_graph import _term_pattern
        model_sources = []
        for source in sources:
            target = _term_pattern((targets or {}).get(source.get("corpus"), []))
            lines = source["excerpt"].splitlines()
            relevant = [line for line in lines if target and target.search(line)]
            model_sources.append(dict(source=source["index"], document=source["document_name"],
                                      excerpt="\n".join(relevant or lines)))
        prompt = (
            "증상 질문의 관련 조건들을 비교하는 JSON을 작성하세요. manual_examples에는 서로 다른 조건을 설명하는 "
            "직접 근거를 필요한 만큼 고르세요. 같은 출처에도 서로 다른 조건이 있으면 각각 인용하세요. source에는 해당 근거 번호를 쓰세요. quote는 해당 출처 한 줄에서 "
            "조건과 결과가 드러나는 짧은 원문 한 문장을 그대로 복사하세요. 줄 하나로 뜻을 알 수 있는 장비 측 조건을 우선하고 반복은 생략하세요. "
            "알람 표는 해당 증상과 직접 관련되고 새로운 정보를 줄 때만 번호와 설명이 있는 행을 고르세요. "
            "절차나 조작 지시는 예시로 고르지 마세요. first_check에는 현장에서 어떤 조건에 해당하는지 구분할 "
            "관찰 항목을 필요한 만큼 설명하세요. 미확인 원인이나 알람 발생을 단정하지 마세요."
        )
    messages = [{"role": "system", "content": instructions + "\n" + ANSWER_SNIPPET_SELECTION + "\n" + prompt},
                    {"role": "user", "content": json.dumps({"question": question, "sources": model_sources}, ensure_ascii=False)}]
    content, finish = await graph_completion(config, messages, schema)
    if finish == "length":
        messages[0]["content"] += "\n간략 형식으로 작성하세요. 서로 다른 관련 조건은 유지하되 각 인용은 필요한 원문 한 문장 또는 표 한 행으로 줄이세요. 알람 목록을 나열하지 마세요."
        content, _ = await graph_completion(config, messages, schema)
    plan = schema.model_validate_json(content)
    if isinstance(plan, DiagnosticAnswer):
        return format_diagnostic(plan, [{"index": s["source"], "excerpt": s["excerpt"]} for s in model_sources])
    return format_answer(plan, question, sources)
