import json
import re
from dataclasses import dataclass

from backend.app.core.llm_handler import BaseLLM
from backend.app.core.prompt_manager import PromptManager

@dataclass
class OpenIEResult:
    chunk_id: str
    triples: list[tuple[str, str, str]]
    raw: str


def _extract_json_array(text: str) -> list | None:
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\[\s*\[.*\]\s*\]", text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _coerce_triple(item) -> tuple[str, str, str] | None:
    if not isinstance(item, (list, tuple)) or len(item) != 3:
        return None
    s, p, o = (str(x).strip() for x in item)
    if not (s and p and o):
        return None
    # cheap filters
    if len(s) > 120 or len(p) > 80 or len(o) > 200:
        return None
    return (s, p, o)


def extract_triples(
    llm: BaseLLM,
    chunk_id: str,
    passage: str,
    max_new_tokens: int = 300,
) -> OpenIEResult:
    """Single-chunk triple extraction. Returns up to ~10 triples per chunk."""
    prompt_manager = PromptManager()
    messages = prompt_manager.build_kg_prompt(text=passage.strip())
    raw = llm.invoke(messages)
    arr = _extract_json_array(raw) or []
    triples: list[tuple[str, str, str]] = []
    for it in arr:
        t = _coerce_triple(it)
        if t and t not in triples:
            triples.append(t)
    return OpenIEResult(chunk_id=chunk_id, triples=triples, raw=raw)

def extract_triples_batch(llm: BaseLLM, chunks: list[tuple[str, str]], stream_path=None):
    out: list[OpenIEResult] = []
    iterable = chunks
    sink = None
    if stream_path is not None:
        sink = open(stream_path, "a")
    try:
        for cid, text in iterable:
            r = extract_triples(llm, cid, text)
            out.append(r)
            if sink is not None:
                sink.write(json.dumps({"chunk_id": r.chunk_id, "triples": r.triples}) + "\n")
                sink.flush()
    finally:
        if sink is not None:
            sink.close()
    return out