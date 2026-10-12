"""XSYMBOL.000 (심볼/코멘트 테이블) 파서.

탭 구분 텍스트. 각 줄: 주소 \t 심볼 \t 짧은 코멘트 \t 코멘트 \t ...
예) 'X00003.0\t/MD1.X\t\tMODE SELECT 1\t\t\t\t\t\t'

C:\\workspace\\repos\\2026\\Fanuc_LAD_Decode\\fanuc_lad\\symbols.py를 그대로 포팅.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from .model import Address


@dataclass
class Symbol:
    address: Address
    symbol: str
    short: str = ""
    comment: str = ""
    fields: List[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        return str(self.address)


def parse_symbols(data: bytes, encoding: str = "cp949") -> List[Symbol]:
    text = data.decode(encoding, errors="replace")
    out: List[Symbol] = []
    for line in text.splitlines():
        fields = line.rstrip("\r").split("\t")
        if len(fields) < 2 or not fields[0].strip():
            continue
        try:
            addr = Address.parse(fields[0])
        except ValueError:
            continue
        short = fields[2] if len(fields) > 2 else ""
        comment = fields[3] if len(fields) > 3 else ""
        out.append(Symbol(addr, fields[1], short, comment, fields))
    return out


def symbol_lookup(symbols: List[Symbol]) -> Dict[str, Symbol]:
    """'X3.0' / 'G10' 같은 주소 문자열 -> Symbol."""
    return {s.key: s for s in symbols}
