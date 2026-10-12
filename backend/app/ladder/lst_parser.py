"""LADDER-III .LST(니모닉 텍스트 export) 파서.

`.LST`는 `%@0`~`%@5` 마커로 섹션을 나누고(sysparam/title/symbols/ladder mnemonics/
messages/io-modules), 각 섹션은 단독 `%` 줄로 끝난다. 이번 기능에서 필요한 건 심볼
섹션(`%@2`류)과 래더 니모닉 섹션(`%@3`)뿐이라 이 둘만 파싱한다.

참고 프로젝트(Fanuc_LAD_Decode)는 구조화 데이터 -> .LST 텍스트(mnemonic.render_lst)
방향만 있고 반대 방향(텍스트 -> 구조화 데이터) 파서가 없어서, 이 파일은 그 출력 포맷을
거꾸로 읽는 신규 구현이다. 확인된 실제 LADDER-III 내보내기 샘플이 아직 없어서(계획 문서
"열린 위험" 참고), 멀티레벨(.LST 하나에 LEVEL1~3이 섞인) 구분은 1차 버전에서 지원하지
않고 `%@3` 전체를 단일 프로그램으로 취급한다 - 실제 샘플 확보 후 보강 필요.
"""
from __future__ import annotations

import re
import shlex
from typing import Dict, List, Tuple

from .model import Address, BASIC_OPS, STACK_OPS, Step
from .symbols import Symbol

_SECTION_START_RE = re.compile(r"^%@(\S+)")
_OPNAME_TO_CODE = {name: code for code, name in BASIC_OPS.items()}
_STACK_OP_NAMES = {BASIC_OPS[c] for c in STACK_OPS}


def split_sections(text: str) -> Dict[str, List[str]]:
    """`%@N` ~ `%` 사이를 섹션별 줄 목록으로 나눈다."""
    sections: Dict[str, List[str]] = {}
    current_key = None
    current_lines: List[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        m = _SECTION_START_RE.match(stripped)
        if m:
            if current_key is not None:
                sections[current_key] = current_lines
            current_key = m.group(1)
            current_lines = []
            continue
        if stripped == "%":
            if current_key is not None:
                sections[current_key] = current_lines
            current_key = None
            current_lines = []
            continue
        if current_key is not None:
            current_lines.append(line)
    if current_key is not None:
        sections[current_key] = current_lines
    return sections


def _parse_symbol_lines(lines: List[str]) -> List[Symbol]:
    """`%@2`류 섹션: `<주소> <심볼>` 줄 + 뒤따르는 `$1 '짧은코멘트' '코멘트'` 줄."""
    symbols: List[Symbol] = []
    pending: "Symbol | None" = None
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("$"):
            if pending is not None:
                rest = stripped[2:].strip() if len(stripped) > 2 else ""
                try:
                    parts = shlex.split(rest)
                except ValueError:
                    parts = rest.split()
                pending.short = parts[0] if len(parts) > 0 else ""
                pending.comment = parts[1] if len(parts) > 1 else ""
            continue
        tokens = stripped.split(None, 1)
        if not tokens:
            continue
        try:
            addr = Address.parse(tokens[0])
        except ValueError:
            continue
        symbol_name = tokens[1].strip() if len(tokens) > 1 else ""
        pending = Symbol(addr, symbol_name)
        symbols.append(pending)
    return symbols


def _parse_mnemonic_lines(lines: List[str]) -> List[Step]:
    """`%@3` 섹션: 니모닉 텍스트를 다시 Step으로 복원한다.

    `mnemonic.render_lst()`가 만드는 형태의 기계적 역변환:
    - `SUB <n>`                         -> 함수 Step
    - `AND.STK` / `OR.STK` (피연산자 없음) -> 스택 결합 Step
    - `<opname> <addr>`                 -> 기본 Step(주소 피연산자)
    - opcode 없이 주소/숫자만 있는 줄      -> 직전 함수명령의 param/data 피연산자
    """
    steps: List[Step] = []
    idx = 0
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped:
            continue
        tokens = stripped.split()
        head = tokens[0]

        if head == "SUB" and len(tokens) >= 2:
            try:
                sub_no = int(tokens[1])
            except ValueError:
                continue
            steps.append(Step(idx, "func", b"", op="SUB", sub=sub_no))
            idx += 1
            continue

        if head in _STACK_OP_NAMES:
            steps.append(Step(idx, "basic", b"", op=head))
            idx += 1
            continue

        if head in _OPNAME_TO_CODE and len(tokens) >= 2:
            try:
                addr = Address.parse(tokens[1])
            except ValueError:
                continue
            steps.append(Step(idx, "basic", b"", op=head, operand=addr))
            idx += 1
            continue

        # opcode 없이 주소/상수만 있는 줄 - 함수명령 피연산자
        try:
            addr = Address.parse(head)
            steps.append(Step(idx, "param", b"", operand=addr, param_kind=0x90))
            idx += 1
            continue
        except ValueError:
            pass
        try:
            value = int(head)
            steps.append(Step(idx, "data", b"", operand=value))
            idx += 1
            continue
        except ValueError:
            continue

    return steps


def parse_lst(text: str) -> Tuple[List[Step], List[Symbol], List[str]]:
    warnings: List[str] = []
    sections = split_sections(text)

    symbol_lines = sections.get("2") or sections.get("2-C") or []
    ladder_lines = sections.get("3") or []

    if not ladder_lines:
        warnings.append("'%@3'(래더 니모닉) 섹션을 찾지 못했습니다")
    if not symbol_lines:
        warnings.append("'%@2'(심볼) 섹션을 찾지 못했습니다")

    symbols = _parse_symbol_lines(symbol_lines)
    steps = _parse_mnemonic_lines(ladder_lines)
    return steps, symbols, warnings
