from __future__ import annotations

import re


TOKENIZER_VERSION = "technical_regex_v1"


def tokenize_for_bm25(text: str) -> list[str]:
    # Keep BM25 index and query tokenization identical.
    # This preserves technical terms such as X8.4 while splitting Korean words and numbers.
    return re.findall(r"[A-Za-z]+\.?\d*\.?\d*|[\uac00-\ud7a3]+|\d+", str(text).lower())
