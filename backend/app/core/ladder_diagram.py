"""Convert supported mnemonic networks to a state-free SVG data model."""

from typing import Any


def build_ladder_diagram(block: dict[str, Any]) -> dict[str, Any]:
    steps = block.get("steps") or []
    result = {
        "nblock": block.get("nblock", ""),
        "status": "unsupported",
        "instructions": [
            " ".join(str(value) for value in (
                step.get("op"), (step.get("operand") or {}).get("raw"),
                step.get("symbol"), step.get("description"), step.get("sub_instruction"),
            ) if value)
            for step in steps
        ],
    }
    current = None
    stack = []
    coil = None

    def combine(kind, left, right):
        children = []
        for node in (left, right):
            children.extend(node["children"] if node["kind"] == kind else [node])
        return {"kind": kind, "children": children}

    for step in steps:
        op = step.get("op", "")
        if coil is not None:
            return result
        if op in {"AND.STK", "OR.STK"}:
            if current is None or not stack:
                return result
            current = combine("series" if op == "AND.STK" else "parallel", stack.pop(), current)
            continue
        if op not in {"RD", "RD.NOT", "RD.STK", "RD.STK.NOT", "AND", "AND.NOT", "OR", "OR.NOT", "WRT", "WRT.NOT"}:
            return result
        addr = (step.get("operand") or {}).get("normalized")
        if not addr:
            return result
        node = {
            "kind": "contact", "addr": addr, "label": step.get("symbol") or "",
            "description": step.get("description") or "", "neg": op.endswith(".NOT"),
        }
        if op in {"WRT", "WRT.NOT"}:
            if current is None or stack:
                return result
            coil = node
        elif op in {"RD", "RD.NOT"}:
            if current is not None:
                return result
            current = node
        elif op in {"RD.STK", "RD.STK.NOT"}:
            if current is None:
                return result
            stack.append(current)
            current = node
        else:
            if current is None:
                return result
            current = combine("series" if op.startswith("AND") else "parallel", current, node)

    if current is not None and coil is not None and not stack:
        result.update(status="supported", logic=current, coil=coil)
    return result
