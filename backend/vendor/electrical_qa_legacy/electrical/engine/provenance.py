"""Render-cache provenance: refuse to reuse page renders that belong to a different PDF."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def fingerprint(pdf) -> str:
    """PDF 지문. 240MB 파일 전체 해시는 낭비라 크기 + 앞뒤 1MiB만 쓴다(실무상 충분)."""
    p = Path(pdf)
    h = hashlib.sha256()
    sz = p.stat().st_size
    h.update(str(sz).encode())
    with p.open("rb") as f:
        h.update(f.read(1 << 20))
        if sz > (1 << 21):
            f.seek(-(1 << 20), 2)
            h.update(f.read())
    return h.hexdigest()[:24]


def thumb_hash(im: Image.Image) -> str:
    """32×32 dHash — 같은 치수의 **다른 문서**를 구분하는 유일한 수단."""
    g = np.asarray(im.convert("L").resize((33, 32), Image.BILINEAR), dtype=np.int16)
    bits = (g[:, 1:] > g[:, :-1]).flatten()
    return hex(int("".join("1" if b else "0" for b in bits), 2))[2:]


class RenderProvenanceError(RuntimeError):
    """렌더 캐시가 다른 문서의 것일 때. 조용히 잘못된 인덱스를 만드느니 여기서 멈춘다."""


def read_provenance(d) -> dict:
    f = Path(d) / "provenance.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def write_provenance(d, pdf, scale, n_pages, pages=None):
    d = Path(d); d.mkdir(parents=True, exist_ok=True)
    prov = read_provenance(d)
    prov.update({"pdf": str(pdf), "fingerprint": fingerprint(pdf),
                 "scale": scale, "n_pages": n_pages})
    prov.setdefault("pages", {})
    if pages:
        prov["pages"].update(pages)
    (d / "provenance.json").write_text(json.dumps(prov, ensure_ascii=False, indent=1))
    return prov


def check_provenance(d, doc_key, scale=None):
    """디렉터리가 이 문서 것인지 확인. 기록이 없으면 통과(신규 디렉터리)."""
    prov = read_provenance(d)
    if not prov:
        return prov
    if doc_key and prov.get("fingerprint") and prov["fingerprint"] != doc_key:
        raise RenderProvenanceError(
            f"{d} 는 다른 문서의 렌더다 (기록 {prov['fingerprint']}, 요청 {doc_key}). "
            f"기록된 PDF: {prov.get('pdf')}")
    if scale is not None and prov.get("scale") not in (None, scale):
        raise RenderProvenanceError(f"{d} 는 scale {prov['scale']}로 렌더됐다 (요청 {scale})")
    return prov


