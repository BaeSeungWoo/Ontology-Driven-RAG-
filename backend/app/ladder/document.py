"""업로드된 .LAD/.LST를 읽어 프론트에 내려줄 JSON 직렬화 가능한 dict로 만든다.

.LAD/.LST 둘 다 같은 출력 모양으로 합친다:
  {
    "symbols": { "<주소>": {"symbol":..., "short":..., "comment":...}, ... },
    "ladders": [ { "name":..., "label":..., "nets": [ <net>, ... ] }, ... ],
    "meta": {...},
  }
각 net의 모양은 ladder/topology.py의 build_net() 참고.
"""
from __future__ import annotations

from typing import BinaryIO, Dict, List, Union

from .container import LadFile
from .lst_parser import parse_lst
from .model import Step, decode_ladder, group_nets
from .symbols import Symbol, parse_symbols, symbol_lookup
from .topology import build_net


def _symbols_to_dict(symbol_map: Dict[str, Symbol]) -> Dict[str, dict]:
    return {
        key: {"symbol": s.symbol, "short": s.short, "comment": s.comment}
        for key, s in symbol_map.items()
    }


def _build_nets(steps: List[Step], label: str, symbol_map: Dict[str, Symbol]) -> List[dict]:
    nets = []
    for i, net_steps in enumerate(group_nets(steps), start=1):
        try:
            nets.append(build_net(net_steps, i, label, symbol_map))
        except Exception as e:  # 한 네트가 깨져도 나머지는 계속 보여준다
            nets.append({
                "netIndex": i,
                "program": label,
                "outputs": [],
                "warnings": [f"net 파싱 실패: {e}"],
            })
    return nets


def load_lad(file_obj: Union[str, BinaryIO]) -> dict:
    """.LAD(ZIP) 파일을 읽어 문서 dict를 만든다."""
    with LadFile(file_obj) as lad:
        symbols: List[Symbol] = []
        if lad.has("XSYMBOL.000"):
            symbols = parse_symbols(lad.read("XSYMBOL.000"))
        symbol_map = symbol_lookup(symbols)

        ladders = []
        for name in lad.ladder_member_names():
            data = lad.read(name)
            steps = decode_ladder(data)
            label = name.split(".")[0]
            ladders.append({
                "name": name,
                "label": label,
                "nets": _build_nets(steps, label, symbol_map),
            })

    return {
        "symbols": _symbols_to_dict(symbol_map),
        "ladders": ladders,
        "meta": {"source": "lad"},
    }


def load_lst(text: str) -> dict:
    """.LST(니모닉 텍스트) 파일을 읽어 문서 dict를 만든다.

    멀티레벨 경계 마커가 확인되지 않아(ladder/lst_parser.py 모듈 docstring 참고), 1차
    버전은 '%@3' 전체를 단일 프로그램("ALL")으로 취급한다.
    """
    steps, symbols, warnings = parse_lst(text)
    symbol_map = symbol_lookup(symbols)
    label = "ALL"

    return {
        "symbols": _symbols_to_dict(symbol_map),
        "ladders": [{
            "name": "LST",
            "label": label,
            "nets": _build_nets(steps, label, symbol_map),
        }],
        "meta": {"source": "lst", "warnings": warnings},
    }
