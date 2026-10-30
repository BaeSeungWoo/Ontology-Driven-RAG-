from __future__ import annotations

from typing import Any

def machine_documents(info: dict, kind: str | None = None) -> list[str]:
    documents = info.get("document") or []
    if isinstance(documents, dict):
        return list(documents.get(kind, [])) if kind else [
            name for group in ("manual", "controller", "electrical", "ladder") for name in documents.get(group, [])
        ]
    return list(documents)


def build_doc_to_machine_index(machines: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    doc_to_machine = {}
    for machine_code, info in machines.items():
        for doc_name in machine_documents(info):
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
