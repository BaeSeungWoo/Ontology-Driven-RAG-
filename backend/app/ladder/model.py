"""래더 바이너리(LEVELn.#LA) 디코더.

멤버 구조: u32 LE 셀 개수 + 6바이트 셀 × 개수.
셀 = [b0 종류][b1 코드][4바이트 페이로드]
  b0=0x00 기본 명령 : b1=명령 코드, 페이로드=[영역|0x80][바이트 주소 하위][상위][비트]
  b0=0x80 기능 명령 : b1=SUB 번호
  b0=0x81 파라미터 : b1=0x90 주소 [영역][하위][상위][비트], 그 외 상수 i32 LE
  b0=0x82 테이블 데이터 : i32 LE (CODB 변환 테이블 등)

C:\\workspace\\repos\\2026\\Fanuc_LAD_Decode\\fanuc_lad\\ladder.py를 그대로 포팅.
모듈명은 `ladder` 패키지 자신과 겹치지 않게 `model`로 뒀다.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from typing import List, Optional, Union

CELL_SIZE = 6

# 영역 코드. 1~6, 8 은 실제 파일로 검증, 7/9/10 은 FANUC 주소 순서(C, D, T)에 따른 추정.
AREA_CODES = {1: "X", 2: "Y", 3: "F", 4: "G", 5: "R", 6: "A", 7: "C", 8: "K", 9: "D", 10: "T"}

BASIC_OPS = {
    0x01: "RD", 0x02: "RD.NOT",
    0x03: "AND", 0x04: "AND.NOT",
    0x05: "OR", 0x06: "OR.NOT",
    0x07: "RD.STK", 0x08: "RD.STK.NOT",
    0x14: "AND.STK", 0x15: "OR.STK",
    0x1E: "WRT", 0x1F: "WRT.NOT",
}
STACK_OPS = {0x14, 0x15}          # 피연산자 없음

SUB_NAMES = {
    1: "END1", 2: "END2", 3: "TMR", 4: "DEC", 5: "CTR", 6: "ROT", 7: "COD", 8: "MOVE",
    9: "COM", 10: "JMP", 11: "PARI", 14: "DCNV", 15: "COMP", 16: "COIN", 17: "DSCH",
    18: "XMOV", 19: "ADD", 20: "SUB", 21: "MUL", 22: "DIV", 23: "NUME", 24: "TMRB",
    25: "DECB", 26: "ROTB", 27: "CODB", 28: "MOVOR", 29: "COME", 30: "JMPE", 31: "DCNVB",
    32: "COMPB", 33: "SFT", 34: "DSCHB", 35: "XMOVB", 36: "ADDB", 37: "SUBB", 38: "MULB",
    39: "DIVB", 40: "NUMEB", 41: "DISPB", 42: "EXIN", 43: "MOVB", 44: "MOVW", 45: "MOVN",
    47: "MOVD", 48: "END3", 51: "WINDR", 52: "WINDW", 53: "AXCTL",
    54: "TMRC", 55: "CTRC", 56: "CTRB", 57: "DIFU", 58: "DIFD", 59: "EOR", 60: "AND",
    61: "OR", 62: "NOT", 63: "MMC3R", 64: "END", 65: "CALL", 66: "CALLU", 67: "MMC3W",
    68: "JMPB", 69: "LBL", 71: "SP", 72: "SPE", 73: "JMPC", 86: "SPCNT",
    88: "MMCWR", 89: "MMCWW", 90: "FNC90", 91: "FNC91", 92: "FNC92", 93: "FNC93",
    94: "FNC94", 95: "FNC95", 96: "FNC96", 97: "FNC97",
}

# END1/END2/END - 회로 로직이 없는 레벨/프로그램 경계 마커. 래더뷰 렌더링에서 제외한다.
NON_LOGIC_SUBS = {1, 2, 64}

_ADDR_RE = re.compile(r"^([A-Z])(\d+)(?:\.(\d))?$")


@dataclass(frozen=True)
class Address:
    """PMC 주소. bit 가 None 이면 바이트 주소."""

    area: str
    byte: int
    bit: Optional[int] = None

    def __str__(self) -> str:
        return f"{self.area}{self.byte}" + (f".{self.bit}" if self.bit is not None else "")

    @classmethod
    def parse(cls, text: str) -> "Address":
        m = _ADDR_RE.match(text.strip().upper())
        if not m:
            raise ValueError(f"주소 형식이 아님: {text!r}")
        return cls(m.group(1), int(m.group(2)), int(m.group(3)) if m.group(3) is not None else None)


@dataclass
class Step:
    """래더 셀 하나를 디코딩한 결과."""

    index: int
    kind: str                      # basic | func | param | data | unknown
    raw: bytes
    op: str = ""                   # basic: 명령 이름, func: "SUB"
    operand: Union[Address, int, None] = None
    sub: Optional[int] = None      # func 일 때 SUB 번호
    param_kind: Optional[int] = None

    @property
    def opcode(self) -> int:
        return self.raw[1]

    @property
    def sub_name(self) -> Optional[str]:
        if self.sub is None:
            return None
        return SUB_NAMES.get(self.sub, f"SUB{self.sub}")

    @property
    def is_net_start(self) -> bool:
        # raw(원본 6바이트 셀)가 없는 .LST 경유 Step도 있어서(ladder/lst_parser.py),
        # opcode(=raw[1]) 대신 op 이름 문자열로 판정한다.
        return self.kind == "basic" and self.op in ("RD", "RD.NOT")

    @property
    def ends_net(self) -> bool:
        if self.kind == "basic":
            return self.op in ("WRT", "WRT.NOT")
        return True  # 기능 명령/파라미터 뒤에 오는 RD 는 새 넷


def _address(cell: bytes, keep_zero_bit: bool) -> Address:
    code = cell[2] & 0x7F
    area = AREA_CODES.get(code, f"?{code:02X}")
    byte = cell[3] | (cell[4] << 8)
    bit: Optional[int] = cell[5]
    if not keep_zero_bit and bit == 0:
        bit = None
    return Address(area, byte, bit)


def decode_cell(index: int, cell: bytes) -> Step:
    b0, b1 = cell[0], cell[1]
    if b0 == 0x00:
        op = BASIC_OPS.get(b1, f"OP_{b1:02X}")
        if b1 in STACK_OPS:
            return Step(index, "basic", cell, op=op)
        return Step(index, "basic", cell, op=op, operand=_address(cell, keep_zero_bit=True))
    if b0 == 0x80:
        return Step(index, "func", cell, op="SUB", sub=b1)
    if b0 == 0x81:
        if b1 == 0x90:
            return Step(index, "param", cell, operand=_address(cell, keep_zero_bit=False), param_kind=b1)
        return Step(index, "param", cell, operand=struct.unpack_from("<i", cell, 2)[0], param_kind=b1)
    if b0 == 0x82:
        return Step(index, "data", cell, operand=struct.unpack_from("<i", cell, 2)[0], param_kind=b1)
    return Step(index, "unknown", cell)


def decode_ladder(data: bytes) -> List[Step]:
    """LEVELn.#LA 멤버 바이트열을 Step 목록으로 디코딩한다."""
    if len(data) < 4:
        return []
    count = struct.unpack_from("<I", data, 0)[0]
    available = (len(data) - 4) // CELL_SIZE
    steps: List[Step] = []
    for i in range(min(count, available)):
        off = 4 + i * CELL_SIZE
        steps.append(decode_cell(i, data[off:off + CELL_SIZE]))
    return steps


def declared_count(data: bytes) -> int:
    return struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else 0


def group_nets(steps: List[Step]) -> List[List[Step]]:
    """WRT/기능 명령 뒤에 오는 RD/RD.NOT 를 새 넷의 시작으로 보고 묶는다."""
    nets: List[List[Step]] = []
    current: List[Step] = []
    prev_end = True
    for s in steps:
        if s.is_net_start and prev_end and current:
            nets.append(current)
            current = []
        current.append(s)
        prev_end = s.ends_net
    if current:
        nets.append(current)
    return nets
