from __future__ import annotations

from typing import Any

def build_doc_to_machine_index(machines: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    doc_to_machine = {}
    for machine_code, info in machines.items():
        for doc_name in info.get("document", []):
            key = doc_name
            doc_to_machine.setdefault(key, []).append(machine_code)

    return doc_to_machine

def _resolve_machine_code(source_doc_name: str, doc_to_machine: dict[str, list[str]]) -> list[str]:
    key = source_doc_name
    if key in doc_to_machine:
        return doc_to_machine[key]

    matched: list[str] = []
    for doc_name, machine_codes in doc_to_machine.items():
        if key in doc_name or doc_name in key:
            matched.extend(machine_codes)

    return sorted(set(matched))

def enrich_machine_codes(chunks: list[dict[str, Any]], doc_to_machine: dict[str, list[str]]) -> list[dict[str, Any]]:
    enriched = []

    for chunk in chunks:
        source_doc_name = chunk["metadata"].get("source_doc_name", "")
        machine_codes = _resolve_machine_code(source_doc_name, doc_to_machine)

        new_chunk = dict(chunk)
        metadata = dict(new_chunk["metadata"])
        metadata["machine_code"] = machine_codes
        new_chunk["metadata"] = metadata
        enriched.append(new_chunk)

    return enriched