from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, Any

# region 섹션별 상수
SECTION_SYMBOLS: Final = "%@2-C"
SECTION_LADDER: Final = "%@3"
SECTION_ALARMS: Final = "%@4"
# endregion

# region 데이터 모델 정의
# 주소사전
@dataclass(frozen=True, slots=True)
class SymbolDictionaryEntry:
    address: LadderOperand
    symbol: str | None
    description: str | None

# X8.4 같은 신호를 검색하기 용이하도록 X0084처럼 확장
@dataclass(frozen=True, slots=True)
class LadderOperand:
    raw: str
    device: str
    word: int
    bit: int | None
    normalized: str
    drawing_code: str
    signal_type: str

# 알람구역 구조
@dataclass(frozen=True, slots=True)
class AlarmEntry:
    address: LadderOperand
    alarm_code: str
    message: str | None

# SUB 구조
@dataclass(frozen=True, slots=True)
class SubInstructionArgument:
    value: str
    symbol: str | None
    description: str | None


@dataclass(frozen=True, slots=True)
class SubInstruction:
    code: int
    name: str | None
    arguments: list[SubInstructionArgument]

# ladder 한줄
@dataclass(frozen=True, slots=True)
class LadderStep:
    op: str
    role: str
    stack_op: str | None
    operand: LadderOperand | None
    symbol: str | None
    description: str | None
    sub_instruction: SubInstruction | None = None

# N블록 요약
@dataclass(frozen=True, slots=True)
class LadderNBlockSummary:
    read_operands: list[str]
    write_operands: list[str]
    input_signals: list[str]
    output_signals: list[str]
    internal_signals: list[str]

# N블록
@dataclass(frozen=True, slots=True)
class LadderNBlock:
    nblock: str
    summary: LadderNBlockSummary
    search_text: str
    has_stack_logic: bool
    logic_expression: str | None
    logic_confidence: str
    steps: list[LadderStep]

# 논리 우선순위
@dataclass(frozen=True, slots=True)
class LogicNode:
    operator: str | None
    label: str | None
    children: tuple["LogicNode", ...]
# endregion

# region Section extraction
# 지정한 %@ 구역을 잘라내는 함수
def extract_section(text: str, section: str) -> list[str]:
    lines = text.splitlines()
    in_section = False
    section_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped == section:
            in_section = True
            continue

        if in_section and stripped.startswith("%@"):
            break

        if in_section:
            section_lines.append(line)

    return section_lines
# endregion

# region Symbol and alarm parsing
# %@2-c 구역 정규식
SYMBOL_ENTRY_RE: Final = re.compile(r"^(?P<address>[A-Z]\d+(?:\.\d+)?)(?:\s+(?P<symbol>\S+))?\s*$")
SYMBOL_DESCRIPTION_RE: Final = re.compile(r"^\$1\s+''\s+'(?P<description>.*)'\s*$")
# %@3
STEP_RE: Final = re.compile(r"^(?:(N\d+):\s*)?(?P<op>[A-Z][A-Z0-9.]*)(?:\s+(?P<operand>[A-Z]\d+(?:\.\d+)?))?\s*(?:;\((?P<symbol>[^)]*)\))?")
SUB_RE: Final = re.compile(r"^(?:(?P<nblock>N\d+):\s*)?SUB\s+(?P<code>\d+)(?:\s*;\s*(?P<name>.*\S))?\s*$")
DESCRIPTION_RE: Final = re.compile(r"^\s*;\[(?P<description>.*)\]\s*$")
OPERAND_RE: Final = re.compile(r"^(?P<device>[A-Z])(?P<word>\d+)(?:\.(?P<bit>\d+))?$")
# %@4
ALARM_ENTRY_RE: Final = re.compile(r"^(?P<address>A\d+(?:\.\d+)?)\s+(?P<code>\d+)(?:\s+(?P<message>.*\S))?\s*$")

# 신호 정의
def get_signal_type(device: str) -> str:
    signal_types = {
        "X": "input",
        "Y": "output",
        "R": "internal_relay",
        "F": "cnc_to_pmc",
        "G": "pmc_to_cnc",
        "A": "alarm",
        "T": "timer",
        "C": "counter",
        "K": "keep_relay",
        "D": "data_register/data_memory",
        "E": "shared_memory",
        "P": "program/parameter/etc"
    }
    return signal_types.get(device, "unknown")

# 신호 정규화
def parse_operand(raw: str | None) -> LadderOperand | None:
    if raw is None:
        return None

    match = OPERAND_RE.match(raw)
    if match is None:
        return None

    device = match.group("device")
    word = int(match.group("word"))
    bit_text = match.group("bit")
    bit = int(bit_text) if bit_text is not None else None

    normalized = f"{device}{word}"
    if bit is not None:
        normalized = f"{normalized}.{bit}"

    drawing_code = f"{device}{word:03d}"
    if bit is not None:
        drawing_code = f"{drawing_code}{bit}"

    return LadderOperand(
        raw=raw,
        device=device,
        word=word,
        bit=bit,
        normalized=normalized,
        drawing_code=drawing_code,
        signal_type=get_signal_type(device),
    )

# 주소/심볼사전 항목 정규화
def parse_symbol_entries(lines: list[str]) -> list[SymbolDictionaryEntry]:
    entries: list[SymbolDictionaryEntry] = []
    current_entry: SymbolDictionaryEntry | None = None

    for line in lines:
        stripped = line.strip()

        entry_match = SYMBOL_ENTRY_RE.match(stripped)
        if entry_match is not None:
            if current_entry is not None:
                entries.append(current_entry)

            address = parse_operand(entry_match.group("address"))
            if address is None:
                current_entry = None
                continue

            symbol = entry_match.group("symbol")

            current_entry = SymbolDictionaryEntry(
                address=address,
                symbol=symbol.strip() if symbol is not None else None,
                description=None,
            )
            continue

        description_match = SYMBOL_DESCRIPTION_RE.match(stripped)
        if description_match is not None and current_entry is not None:
            current_entry = SymbolDictionaryEntry(
                address=current_entry.address,
                symbol=current_entry.symbol,
                description=description_match.group("description").strip(),
            )

    if current_entry is not None:
        entries.append(current_entry)

    return entries

# 알람 항목 정규화
def parse_alarm_entries(lines: list[str]) -> list[AlarmEntry]:
    entries: list[AlarmEntry] = []

    for line in lines:
        match = ALARM_ENTRY_RE.match(line.strip())
        if match is None:
            continue

        address = parse_operand(match.group("address"))
        if address is None:
            continue

        entries.append(
            AlarmEntry(
                address=address,
                alarm_code=f"AL{match.group('code')}",
                message=match.group("message"),
            )
        )

    return entries
# endregion

# region Ladder analysis
# 논리(role) 정의
def get_step_role(op: str) -> str:
    roles = {
        "RD": "read",
        "RD.NOT": "read_not",
        "AND": "condition_and",
        "AND.NOT": "condition_and_not",
        "OR": "condition_or",
        "OR.NOT": "condition_or_not",
        "WRT": "write",
        "WRT.NOT": "write_not",
        "RD.STK": "stack_read",
        "RD.STK.NOT": "stack_read_not",
        "OR.STK": "stack_or",
        "AND.STK": "stack_and",
        "SUB": "sub_instruction",
    }
    return roles.get(op, "unknown")

# STK 정의
def get_stack_op(op: str) -> str | None:
    stack_ops = {
        "RD.STK": "start_stack_group",
        "RD.STK.NOT": "start_stack_group",
        "OR.STK": "merge_stack_group_with_or",
        "AND.STK": "merge_stack_group_with_and",
    }
    return stack_ops.get(op)

# 중복제거
def unique_sorted(values: list[str]) -> list[str]:
    return sorted(set(values))

# N블록 요약 summary 생성
def build_nblock_summary(steps: list[LadderStep]) -> LadderNBlockSummary:
    read_operands: list[str] = []
    write_operands: list[str] = []
    input_signals: list[str] = []
    output_signals: list[str] = []
    internal_signals: list[str] = []

    for step in steps:
        operand = step.operand
        if operand is None:
            continue

        if step.role.startswith("read") or step.role.startswith("condition") or step.role.startswith("stack"):
            read_operands.append(operand.normalized)

        if step.role.startswith("write"):
            write_operands.append(operand.normalized)

        if operand.signal_type == "input":
            input_signals.append(operand.drawing_code)

        if operand.signal_type == "output":
            output_signals.append(operand.drawing_code)

        if operand.signal_type == "internal_relay":
            internal_signals.append(operand.drawing_code)

    return LadderNBlockSummary(
        read_operands=unique_sorted(read_operands),
        write_operands=unique_sorted(write_operands),
        input_signals=unique_sorted(input_signals),
        output_signals=unique_sorted(output_signals),
        internal_signals=unique_sorted(internal_signals),
    )

# step을 짧은 문장으로 바꾸는 함수 (searchText)
def format_step_for_search(step: LadderStep) -> str:
    parts: list[str] = [step.role]

    if step.operand is not None:
        parts.append(step.operand.normalized)
        parts.append(step.operand.drawing_code)
        parts.append(step.operand.signal_type)

    if step.symbol is not None:
        parts.append(step.symbol)

    if step.description is not None:
        parts.append(step.description)

    return " ".join(parts)

# searchText 생성
def build_search_text(nblock: str, steps: list[LadderStep]) -> str:
    step_texts = [format_step_for_search(step) for step in steps]
    return f"{nblock} " + " | ".join(step_texts)

# 주소를 보기좋게 변환
def format_operand_label(step: LadderStep) -> str:
    if step.operand is None:
        return ""

    label = step.operand.normalized

    if step.symbol is not None:
        label = f"{label}({step.symbol})"

    return label

def format_condition_label(step: LadderStep) -> str:
    label = format_operand_label(step)

    if step.op in {"RD.NOT", "RD.STK.NOT", "AND.NOT", "OR.NOT"}:
        return f"NOT {label}"

    return label

# STK가 있는지 확인
def has_stack_steps(steps: list[LadderStep]) -> bool:
    return any(step.stack_op is not None for step in steps)

# 논리 노드 생성
def make_logic_leaf(label: str) -> LogicNode:
    return LogicNode(
        operator=None,
        label=label,
        children=(),
    )

# and는 and끼리, or은 or끼리 하나의 묶음처리
def combine_logic(
    operator: str,
    left: LogicNode,
    right: LogicNode,
) -> LogicNode:
    children: list[LogicNode] = []

    for node in (left, right):
        if node.operator == operator:
            children.extend(node.children)
        else:
            children.append(node)

    return LogicNode(
        operator=operator,
        label=None,
        children=tuple(children),
    )

def render_logic_node(node: LogicNode) -> str:
    if node.operator is None:
        return node.label or ""

    child_texts = [
        render_logic_node(child)
        for child in node.children
    ]

    return f"({f' {node.operator} '.join(child_texts)})"

def format_sub_instruction_label(step: LadderStep) -> str:
    if step.sub_instruction is None:
        return "SUB"

    label = f"SUB {step.sub_instruction.code}"

    if step.sub_instruction.name is not None:
        label = f"{label} ({step.sub_instruction.name})"

    return label

# 조건식 생성 함수
def build_logic_expression(steps: list[LadderStep]) -> str | None:
    current_expression: LogicNode | None = None
    expression_stack: list[LogicNode] = []
    writes: list[str] = []
    sub_instructions: list[str] = []

    for step in steps:
        if step.role.startswith("write"):
            label = format_operand_label(step)

            if label:
                writes.append(label)

            continue

        if step.op in {"OR.STK", "AND.STK"}:
            if current_expression is None or not expression_stack:
                return None

            previous_expression = expression_stack.pop()
            operator = "OR" if step.op == "OR.STK" else "AND"

            current_expression = combine_logic(
                operator,
                previous_expression,
                current_expression,
            )
            continue

        if step.op == "SUB":
            if current_expression is None:
                if expression_stack:
                    return None

                sub_instructions.append(format_sub_instruction_label(step))
                continue

            if expression_stack:
                stack_text = ", ".join(
                    render_logic_node(expression)
                    for expression in expression_stack
                )
                sub_instructions.append(
                    f"{format_sub_instruction_label(step)} [stack: {stack_text}]"
                )
                expression_stack.clear()
            else:
                sub_instructions.append(format_sub_instruction_label(step))

            continue

        label = format_condition_label(step)

        if not label:
            continue

        if step.op in {"RD", "RD.NOT"}:
            current_expression = make_logic_leaf(label)
            continue

        if step.op in {"RD.STK", "RD.STK.NOT"}:
            if current_expression is not None:
                expression_stack.append(current_expression)

            current_expression = make_logic_leaf(label)
            continue

        if step.op in {"AND", "AND.NOT"}:
            operand_node = make_logic_leaf(label)

            if current_expression is None:
                current_expression = operand_node
            else:
                current_expression = combine_logic(
                    "AND",
                    current_expression,
                    operand_node,
                )

            continue

        if step.op in {"OR", "OR.NOT"}:
            operand_node = make_logic_leaf(label)

            if current_expression is None:
                current_expression = operand_node
            else:
                current_expression = combine_logic(
                    "OR",
                    current_expression,
                    operand_node,
                )

            continue

        current_expression = make_logic_leaf(label)

    if expression_stack:
        return None

    targets = sub_instructions + writes
    if not targets:
        return None

    if current_expression is None:
        return " -> ".join(targets)

    return f"{render_logic_node(current_expression)} -> {' -> '.join(targets)}"
# endregion

# region Ladder parsing
# N블록으로 묶기 // 다음 N블록이 오기전까지 라인들을 하나의 블록으로 규합
def parse_ladder_nblocks(lines: list[str]) -> list[LadderNBlock]:
    nblocks: list[LadderNBlock] = []
    current_nblock: str | None = None
    current_steps: list[LadderStep] = []
    pending_step: LadderStep | None = None

    index = 0
    while index < len(lines):
        line = lines[index]

        sub_match = SUB_RE.match(line.strip())
        if sub_match is not None:
            nblock = sub_match.group("nblock")
            if nblock is not None:
                if current_nblock is not None:
                    nblocks.append(
                        LadderNBlock(
                            nblock=current_nblock,
                            summary=build_nblock_summary(current_steps),
                            search_text=build_search_text(current_nblock, current_steps),
                            has_stack_logic=has_stack_steps(current_steps),
                            logic_expression=build_logic_expression(current_steps),
                            logic_confidence="pattern_based" if has_stack_steps(current_steps) else "simple",
                            steps=current_steps,
                        )
                    )

                current_nblock = nblock
                current_steps = []

            if current_nblock is None:
                index += 1
                continue

            arguments: list[SubInstructionArgument] = []
            argument_index = index + 1
            while argument_index < len(lines):
                argument_line = lines[argument_index].strip()
                if not argument_line:
                    argument_index += 1
                    continue

                description_match = DESCRIPTION_RE.match(argument_line)
                if description_match is not None:
                    if arguments:
                        argument = arguments[-1]
                        arguments[-1] = SubInstructionArgument(
                            value=argument.value,
                            symbol=argument.symbol,
                            description=description_match.group("description").strip(),
                        )
                    argument_index += 1
                    continue

                argument_step = STEP_RE.match(argument_line)
                if (
                    re.match(r"^N\d+:", argument_line)
                    or (
                        argument_step is not None
                        and get_step_role(argument_step.group("op")) != "unknown"
                    )
                ):
                    break

                value = argument_line.split(";", 1)[0].strip()
                if value:
                    symbol_match = re.search(r";\((?P<symbol>[^)]*)\)", argument_line)
                    arguments.append(
                        SubInstructionArgument(
                            value=value,
                            symbol=(
                                symbol_match.group("symbol").strip()
                                if symbol_match is not None
                                else None
                            ),
                            description=None,
                        )
                    )
                argument_index += 1

            step = LadderStep(
                op="SUB",
                role=get_step_role("SUB"),
                stack_op=None,
                operand=None,
                symbol=None,
                description=None,
                sub_instruction=SubInstruction(
                    code=int(sub_match.group("code")),
                    name=sub_match.group("name"),
                    arguments=arguments,
                ),
            )
            current_steps.append(step)
            pending_step = step
            index = argument_index
            continue

        description_match = DESCRIPTION_RE.match(line)
        if description_match and pending_step is not None:
            pending_step = LadderStep(
                op=pending_step.op,
                role=pending_step.role,
                stack_op=pending_step.stack_op,
                operand=pending_step.operand,
                symbol=pending_step.symbol,
                description=description_match.group("description").strip(),
                sub_instruction=pending_step.sub_instruction,
            )
            current_steps[-1] = pending_step
            index += 1
            continue

        step_match = STEP_RE.match(line.strip())
        if step_match is None:
            index += 1
            continue

        nblock = step_match.group(1)
        if nblock is not None:
            if current_nblock is not None:
                nblocks.append(
                    LadderNBlock(
                        nblock=current_nblock,
                        summary=build_nblock_summary(current_steps),
                        search_text=build_search_text(current_nblock, current_steps),
                        has_stack_logic=has_stack_steps(current_steps),
                        logic_expression=build_logic_expression(current_steps),
                        logic_confidence="pattern_based" if has_stack_steps(current_steps) else "simple",
                        steps=current_steps,
                    )
                )

            current_nblock = nblock
            current_steps = []

        if current_nblock is None:
            index += 1
            continue

        symbol = step_match.group("symbol")
        
        op = step_match.group("op")
        step = LadderStep(
            op=op,
            role=get_step_role(op),
            stack_op=get_stack_op(op),
            operand=parse_operand(step_match.group("operand")),
            symbol=symbol.strip() if symbol is not None else None,
            description=None,
        )
        current_steps.append(step)
        pending_step = step
        index += 1

    if current_nblock is not None:
        nblocks.append(
            LadderNBlock(
                nblock=current_nblock,
                summary=build_nblock_summary(current_steps),
                search_text=build_search_text(current_nblock, current_steps),
                has_stack_logic=has_stack_steps(current_steps),
                logic_expression=build_logic_expression(current_steps),
                logic_confidence="pattern_based" if has_stack_steps(current_steps) else "simple",
                steps=current_steps,
            )
        )

    return nblocks
# endregion

# region JSON output
def serialize_ladder_step(step: LadderStep) -> dict[str, object]:
    payload = asdict(step)
    if step.sub_instruction is None:
        del payload["sub_instruction"]
    return payload

# 파일을 읽고 %@3 Ladder logic 구역을 JSON으로 저장
def build_ladder_json(input_path: Path, output_path: Path) -> dict[str, Any]:
    text = input_path.read_text(encoding="utf-8")
    section_lines = extract_section(text, SECTION_LADDER)
    nblocks = parse_ladder_nblocks(section_lines)

    payload = {
        "source_file": input_path.name,
        "section": SECTION_LADDER,
        "nblocks": [
            {
                "nblock": nblock.nblock,
                "summary": asdict(nblock.summary),
                "search_text": nblock.search_text,
                "has_stack_logic": nblock.has_stack_logic,
                "logic_expression": nblock.logic_expression,
                "logic_confidence": nblock.logic_confidence,
                "steps": [serialize_ladder_step(step) for step in nblock.steps],
            }
            for nblock in nblocks
        ],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return payload

# 파일을 읽고 %@2-C 주소/심볼 사전 구역을 JSON으로 저장
def build_symbols_json(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    section_lines = extract_section(text, SECTION_SYMBOLS)
    entries = parse_symbol_entries(section_lines)

    payload = {
        "source_file": input_path.name,
        "section": SECTION_SYMBOLS,
        "entries": [asdict(entry) for entry in entries],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# 파일을 읽고 %@4 알람구역을 JSON으로 저장
def build_alram_json(input_path: Path, output_path: Path) -> None:
    text = input_path.read_text(encoding="utf-8")
    section_lines = extract_section(text, SECTION_ALARMS)
    entries = parse_alarm_entries(section_lines)

    payload = {
        "source_file": input_path.name,
        "section": SECTION_ALARMS,
        "entries": [asdict(entry) for entry in entries],
    }

    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# 파일 일괄 생성
def build_mnemonic_files(input_file: Path, output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    ladder_struct = build_ladder_json(input_file, output_dir / "ladder.json")
    build_symbols_json(input_file, output_dir / "symbols.json")
    build_alram_json(input_file, output_dir / "alram.json")
    return ladder_struct
# endregion

# region CLI
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()

    output_dir = (
        Path("pipeline/data")
        / args.site_id
        / "ladder"
        / "struct"
    )

    build_mnemonic_files(args.input, output_dir)
    print(f"created: {output_dir}")
# endregion
