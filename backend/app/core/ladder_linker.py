from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any


ADDRESS_RE = re.compile(r"\b([A-Za-z])(\d+)(?:\.(\d+))?\b")
ALARM_RE = re.compile(r"\bAL\d+\b", re.IGNORECASE)
SYMBOL_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9.*_-]+\b")

COOLANT_PROFILES = {
    "standard_coolant": {
        "label": "일반 절삭유 펌프",
        "keywords": ("절삭유", "coolant", "clt"),
        "search_terms": ("CLTON", "CLTOF", "CLT PM", "M08", "M09", "CLTPMILK", "CLTPMON", "X102.2", "X102.3", "R590.0", "R592.0", "R32.1", "Y0.1"),
        "addresses": ("X102.2", "X102.3", "R2.2", "R2.3", "R590.0", "R592.0", "R32.1", "Y0.1"),
        "seed_nblocks": ("N01262", "N01263", "N01264", "N00352"),
        "description": "일반 절삭유 펌프가 동작하지 않는 증상입니다. CLT ON/CLT OFF 버튼, M08/M09, 펌프 인터록, 펌프 ON 신호와 Y0.1 출력을 확인합니다.",
    },
    "gun_coolant": {
        "label": "건 절삭유",
        "keywords": ("건클린", "건 절삭유", "건절삭유", "gun coolant", "cltgun", "clt gun"),
        "search_terms": ("CLTGUN", "GUN CLT", "GUNCLT"),
        "addresses": (),
        "seed_nblocks": (),
        "description": "건 절삭유 기능의 동작 여부를 확인합니다.",
    },
    "through_coolant": {
        "label": "관통 절삭유",
        "keywords": ("관통", "스루", "through", "thru", "tsc"),
        "search_terms": ("THR CLT", "THRU CLT", "SP THR CLT"),
        "addresses": (),
        "seed_nblocks": (),
        "description": "주축 관통 절삭유 기능의 동작 여부를 확인합니다.",
    },
    "jet_coolant": {
        "label": "젯 절삭유",
        "keywords": ("젯", "jet", "jet coolant"),
        "search_terms": ("JET CLT", "JETCLT"),
        "addresses": (),
        "seed_nblocks": (),
        "description": "젯 절삭유 기능의 동작 여부를 확인합니다.",
    },
    "coolant_cooler": {
        "label": "절삭유 쿨러",
        "keywords": ("쿨러", "냉각기", "cooler"),
        "search_terms": ("CLT COOLER", "CLTCLR"),
        "addresses": (),
        "seed_nblocks": (),
        "description": "절삭유 쿨러 기능 또는 쿨러 알람을 확인합니다.",
    },
}


def normalize_address(value: str) -> str | None:
    match = ADDRESS_RE.fullmatch(str(value).strip())
    if not match:
        return None

    device, word, bit = match.groups()
    address = f"{device.upper()}{int(word)}"
    return f"{address}.{int(bit)}" if bit is not None else address


class LadderLinker:
    def __init__(self, structure_dir: Path):
        ladder_payload = self._load_json(structure_dir / "ladder.json")
        symbols_payload = self._load_json(structure_dir / "symbols.json")
        alarms_payload = self._load_json(structure_dir / "alarm.json")

        self.blocks: dict[str, dict[str, Any]] = {}
        self.writer_blocks: dict[str, list[str]] = defaultdict(list)
        self.reader_blocks: dict[str, list[str]] = defaultdict(list)
        self.address_by_symbol: dict[str, set[str]] = defaultdict(set)
        self.address_by_alarm: dict[str, set[str]] = defaultdict(set)

        self._index_blocks(ladder_payload.get("nblocks") or [])
        self._index_symbols(symbols_payload.get("entries") or [])
        self._index_alarms(alarms_payload.get("entries") or [])

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _index_blocks(self, blocks: list[dict[str, Any]]) -> None:
        for block in blocks:
            nblock = str(block.get("nblock") or "").strip()
            if not nblock:
                continue

            summary = block.get("summary") or {}
            reads = {address for value in summary.get("read_operands") or [] if (address := normalize_address(value))}
            writes = {address for value in summary.get("write_operands") or [] if (address := normalize_address(value))}
            self.blocks[nblock] = {
                "reads": reads,
                "writes": writes,
                "logic_expression": str(block.get("logic_expression") or "").strip(),
            }

            for address in reads:
                self.reader_blocks[address].append(nblock)
            for address in writes:
                self.writer_blocks[address].append(nblock)

            # SEARCH_TERM_DICTIONARY: symbols.json이 비어 있어도 래더 operand 심볼을 주소 사전에 보완한다.
            for step in block.get("steps") or []:
                address = normalize_address((step.get("operand") or {}).get("normalized", ""))
                symbol = str(step.get("symbol") or "").strip().upper()
                if address and symbol:
                    self.address_by_symbol[symbol].add(address)

    def _index_symbols(self, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            address = normalize_address((entry.get("address") or {}).get("normalized", ""))
            if not address:
                continue
            for value in (entry.get("symbol"), entry.get("description")):
                label = str(value or "").strip().upper()
                if label:
                    self.address_by_symbol[label].add(address)

    def _index_alarms(self, entries: list[dict[str, Any]]) -> None:
        for entry in entries:
            address = normalize_address((entry.get("address") or {}).get("normalized", ""))
            code = str(entry.get("alarm_code") or "").strip().upper()
            if address and code:
                self.address_by_alarm[code].add(address)

    @staticmethod
    def build_query_plan(question: str) -> dict[str, Any]:
        normalized = question.casefold()
        profile_name = None

        for name in ("gun_coolant", "through_coolant", "jet_coolant", "coolant_cooler"):
            if any(keyword in normalized for keyword in COOLANT_PROFILES[name]["keywords"]):
                profile_name = name
                break

        if profile_name is None and any(
            keyword in normalized for keyword in COOLANT_PROFILES["standard_coolant"]["keywords"]
        ):
            profile_name = "standard_coolant"

        if profile_name is None:
            return {
                "name": None,
                "label": None,
                "search_terms": [],
                "addresses": [],
                "seed_nblocks": [],
                "expanded_query": question,
            }

        profile = COOLANT_PROFILES[profile_name]
        search_terms = list(profile["search_terms"])
        expanded_query = "\n".join([
            question,
            "[자연어 검색 보강]",
            profile["description"],
            f"[검색 키워드] {' '.join(search_terms)}",
        ])
        return {
            "name": profile_name,
            "label": profile["label"],
            "search_terms": search_terms,
            "addresses": list(profile["addresses"]),
            "seed_nblocks": list(profile["seed_nblocks"]),
            "expanded_query": expanded_query,
        }

    def resolve_addresses(self, text: str) -> set[str]:
        addresses = set()
        for device, word, bit in ADDRESS_RE.findall(text):
            value = f"{device}{word}.{bit}" if bit else f"{device}{word}"
            address = normalize_address(value)
            if address:
                addresses.add(address)

        for code in ALARM_RE.findall(text):
            addresses.update(self.address_by_alarm.get(code.upper(), set()))

        for symbol in SYMBOL_RE.findall(text):
            label = symbol.upper()
            addresses.update(self.address_by_symbol.get(label, set()))

        return addresses

    def expand_search_terms(self, text: str) -> tuple[str, list[str]]:
        plan = self.build_query_plan(text)
        return plan["expanded_query"], plan["search_terms"]

    def linked_addresses(
        self,
        question: str,
        document_texts: list[str],
        profile_addresses: list[str] | None = None,
    ) -> set[str]:
        addresses = self.resolve_addresses(question)
        for value in profile_addresses or []:
            address = normalize_address(value)
            if address:
                addresses.add(address)

        if profile_addresses:
            return addresses

        for text in document_texts:
            addresses.update(self.resolve_addresses(text))
        return addresses

    def rerank(
        self,
        items: list[Any],
        linked_addresses: set[str],
        seed_nblocks: list[str] | None = None,
    ) -> list[Any]:
        seed_nblocks = seed_nblocks or []
        ranked = []
        for original_rank, item in enumerate(items):
            nblock = str(item.metadata.get("section_title") or "").strip()
            block = self.blocks.get(nblock, {})
            block_addresses = set(block.get("reads") or set()) | set(block.get("writes") or set())
            matches = sorted(block_addresses & linked_addresses)
            item.extra["linked_addresses"] = matches
            item.extra["document_ladder_linked"] = bool(matches)
            item.extra["profile_seed"] = nblock in seed_nblocks
            ranked.append((item, matches, original_rank))

        ranked.sort(
            key=lambda value: (
                not value[0].extra["profile_seed"],
                not value[1],
                -len(value[1]),
                value[2],
            )
        )
        return [item for item, _matches, _rank in ranked]

    def trace(self, items: list[Any], intent_type: str, max_depth: int = 2, max_edges: int = 12) -> list[str]:
        upstream = intent_type in {"emergency_action", "troubleshooting", "root_cause_analysis"}
        direction = "원인" if upstream else "사용처"
        lines = [f"[{direction} 래더 추적]"]
        seen_edges: set[tuple[str, str, str]] = set()

        def walk(nblock: str, depth: int) -> None:
            if depth >= max_depth or len(seen_edges) >= max_edges:
                return
            block = self.blocks.get(nblock)
            if not block:
                return

            addresses = block["reads"] if upstream else block["writes"]
            related_index = self.writer_blocks if upstream else self.reader_blocks
            relation = "written by" if upstream else "read by"
            for address in sorted(addresses):
                for related_nblock in related_index.get(address, []):
                    if related_nblock == nblock:
                        continue
                    edge = (nblock, address, related_nblock)
                    if edge in seen_edges:
                        continue
                    seen_edges.add(edge)
                    logic = self.blocks.get(related_nblock, {}).get("logic_expression", "")
                    suffix = f" | {logic}" if logic else ""
                    lines.append(f"- {nblock} -- {address} {relation} --> {related_nblock}{suffix}")
                    walk(related_nblock, depth + 1)
                    if len(seen_edges) >= max_edges:
                        return

        for item in items:
            nblock = str(item.metadata.get("section_title") or "").strip()
            if nblock:
                walk(nblock, 0)
            if len(seen_edges) >= max_edges:
                break

        return lines if len(lines) > 1 else []
