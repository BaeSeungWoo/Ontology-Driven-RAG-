"""PUMA v3 — v2의 세 가지 실패를 한 번에 수정.

v2 진단(RESEARCH_LOG P34~P36):
  ① 절삭유 0/3  : **해상도 부족**. 200DPI 2x2 crop에서 VLM이 아무 어드레스도 못 읽었다.
                  400DPI로 올리니 `X10.6`(gold) 판독. (3x3은 과분할로 오히려 0개)
                  ※ v2의 "성공"으로 보였던 X10.2·Y0.2는 프롬프트 예시에 gold를 써서 생긴
                    **누출**이었다 → 예시에서 실제 어드레스를 제거.
  ② 주축 0/4    : `SPINDLE AMP/MOTOR` 동력 회로로만 가서 PLC 어드레스가 애초에 없음.
  ③ cycle-start : gold 인터록이 여러 시트에 분산.
  ②③의 공통 원인 = **PLC 신호 어드레스는 기능 도면이 아니라 `INPUT SIGNAL`/`OUTPUT RELAY
  CONTROL`/`MACHINE I/O` 전용 시트에 실린다.** 그래서 기능 시트 트랙과 별개로 **신호 시트
  트랙**을 함께 회수하고, 신호 시트는 어드레스가 많으므로 **라벨 적합성으로 걸러** precision을 지킨다.

  LLM_NAME=gemma4 VLLM_API_BASE=http://127.0.0.1:8001/v1 \
  python scripts/run_puma_v3.py --out results/puma_v3.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from metrics import addr_recall
from llm import LLM
from llm import get_logger

log = get_logger("puma_v3")
GOLD = ROOT / "data/example_qa_pair/gold_qa_pairs.json"
CACHE = ROOT / "cache_puma"
PDF_GLOB = "data/electrical-drawing/*PUMA280*.pdf"

# 누출 없는 판독 프롬프트 — 실제 어드레스를 예시로 쓰지 않고 **형식만** 지시한다.
READ_SYS = ("You read a cropped region of an electrical circuit diagram. Find every PLC I/O "
            "address printed on it. A PLC address looks like a letter (X, Y, R, G) + digits + "
            "dot + one digit. For each, also copy the device tag or signal text printed next to "
            'it. Output ONLY a JSON array of objects with keys "address" and "label". '
            "Copy exactly what is printed; do not invent or enumerate. Empty array if none.")
ADDR_RE = re.compile(r"[XYRGF]\d{1,3}\.\d")
SIGNAL_SHEET = re.compile(r"INPUT\s*SIGNAL|OUTPUT\s*RELAY|MACHINE\s*I\s*/\s*O|I/O\s*SYSTEM", re.I)


def render_page(pdf, page, out_dir, scale=4.0):
    """판독용 고해상도 렌더 (200DPI hires로는 어드레스가 안 읽힌다). 캐시."""
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"page_{int(page):04d}.png"
    if not p.exists():
        import pypdfium2 as pdfium
        doc = pdfium.PdfDocument(pdf)
        doc[int(page) - 1].render(scale=scale).to_pil().save(p)
    return p


def read_page(llm, img_path, tmp, page, grid=(2, 2)):
    im = Image.open(img_path)
    W, H = im.size
    R, C = grid
    out = []
    for r in range(R):
        for c in range(C):
            cp = tmp / f"p{int(page):04d}_{R}{C}_{r}{c}.png"
            im.crop((int(W * c / C), int(H * r / R),
                     int(W * (c + 1) / C), int(H * (r + 1) / R))).save(cp)
            try:
                raw = llm.chat_vision(READ_SYS, "이 영역의 PLC 어드레스와 라벨을 JSON 배열로.",
                                      [str(cp)], max_new_tokens=900, temperature=0.0)
            except Exception:
                continue
            # 객체 파싱(라벨 확보) 후, 놓친 어드레스는 느슨 스캔으로 보완
            seen = set()
            for m in re.finditer(r'\{[^{}]*"address"\s*:\s*"([^"]+)"[^{}]*\}', raw):
                a = m.group(1).strip().upper()
                if ADDR_RE.fullmatch(a):
                    lb = re.search(r'"label"\s*:\s*"([^"]*)"', m.group(0))
                    out.append({"address": a, "label": lb.group(1) if lb else "", "page": str(page)})
                    seen.add(a)
            for a in set(ADDR_RE.findall(raw)) - seen:
                out.append({"address": a, "label": "", "page": str(page)})
    return out



def _relevance(entry, qtokens, qrx=()):
    """질문과 항목의 겹침. 절단이 **무엇을 남길지** 정하는 데 쓴다.

    ⚠ `qtokens` 만으로는 이 평가셋에서 **한 번도 동작하지 않는다.** 토큰을
    `[A-Za-z0-9]{3,}` 로 뽑는데 질문이 한국어라 대부분 빈 리스트가 된다(실측:
    DMU85 10문항 중 **9개**, SL2500 9/10, PUMA 8/11 이 ASCII 토큰 0개). 그러면
    호출부의 `_order` 가 기본 `len`(짧은 것 우선)으로 되돌아가 `--cat-relevance` 가
    **구조적으로 무효**가 된다 — 절제에서 이 플래그가 "효과 없음"으로 나온 것은
    잡음이 아니라 이 때문이었다.
    그래서 `qrx`(= `question_subsys(q)` 가 준 **계통 정규식**)로 한국어 질문과
    영문 카탈로그를 잇는다. 이 표는 이미 `--must-subsys`·`demote_generic` 이 쓰는 것과
    같다 — 두 곳에 복사하지 않는다."""
    up = entry.upper()
    n = sum(1 for t in qtokens if t and t in up)
    n += sum(1 for r in qrx if r.search(up))
    return n


def _cap(cat, max_chars, what="", question="", qrx=()):
    """선택 카탈로그를 글자수로 자른다.

    왜: `pick_parts`/`pick_sheets` 는 예외를 잡지 않는다. 카탈로그가 컨텍스트를 넘기면
    llama-server가 HTTP 400을 돌려주고 **1번 문항에서 런 전체가 죽는다**(이미 5.9k 토큰에서
    겪었다). PUMA는 4134/4170자라 12000 상한은 무동작이지만, 310쪽짜리 INTEGREX는 걸린다.
    짧은 항목부터 남겨 최대한 많은 후보를 보존하고, 버린 수를 로그로 남긴다 — 조용한 절단은
    "다 봤는데 못 찾았다"로 읽히기 때문이다."""
    if not max_chars:
        return cat, 0
    total = sum(len(c) + 2 for c in cat)
    if total <= max_chars:
        return cat, 0
    keep, used = [], 0
    # ⚠ 원래는 **짧은 항목부터** 남겼다 — 후보 수를 최대화하는 규칙이라 질문과의
    #   관련성은 아예 안 봤다. 실측: PUMA 24개·DMU 29개 후보가 이 규칙으로 잘렸고,
    #   잘린 쪽에 질문이 찾던 부품이 들어 있었다. `question` 이 오면 **적합도 우선,
    #   동점이면 짧은 것** 순으로 남긴다. question 이 없으면 옛 동작 그대로다.
    _qt = [t for t in re.findall(r"[A-Za-z0-9]{3,}", question.upper())] if question else []
    _order = (lambda c: (-_relevance(c, _qt, qrx), len(c))) if (_qt or qrx) else len
    for c in sorted(cat, key=_order):
        if used + len(c) + 2 > max_chars:
            break
        keep.append(c); used += len(c) + 2
    order = {c: i for i, c in enumerate(cat)}
    keep.sort(key=lambda c: order[c])
    dropped = len(cat) - len(keep)
    if dropped:
        _log = __import__("logging").getLogger("puma_v3")
        _log.warning(f"⚠ {what} 카탈로그 {len(cat)}개 {total}자 → {len(keep)}개 {used}자 "
                     f"({dropped}개 버림, 상한 {max_chars})")
    return keep, dropped


def pick_parts(llm, question, parts, top=6, max_chars=0, relevance=False, qrx=()):
    cat = [f"{p['symbol']}={p['description']}" for p in parts
           if p.get("description") and p.get("sheets")]
    if not cat:
        return []
    cat, _ = _cap(cat, max_chars, "부품", question if relevance else "",
                  qrx if relevance else ())
    raw = llm.chat("CNC 전기회로 진단 전문가. 목록의 태그만 사용.",
                   f"질문: {question}\n\n부품(태그=설명):\n{', '.join(cat)}\n\n"
                   f"이 고장과 직접 관련된 부품을 관련도 순으로 최대 {top}개, 태그만 콤마로 나열:",
                   max_new_tokens=120, temperature=0.0)
    out = []
    for tok in re.split(r"[,\n]", raw):
        t = tok.strip().upper().replace(" ", "")
        if t and not t.startswith("-"):
            t = "-" + t
        if t:
            out.append(t)
    return out[:top]


def pick_sheets(llm, question, titles, top=3, only=None, label="", max_chars=0, relevance=False):
    cat = [f"p{o['page']}={o['title']}" for o in titles
           if o.get("title") and (only is None or only.search(o["title"]))]
    if not cat:
        return []
    cat, _ = _cap(cat, max_chars, "도면제목", question if relevance else "")
    raw = llm.chat("CNC 전기회로도 전문가. 목록의 도면만 고른다.",
                   f"질문: {question}\n\n{label}도면 목록(페이지=제목):\n{', '.join(cat)}\n\n"
                   f"이 고장 진단에 봐야 할 도면을 관련도 순으로 최대 {top}개, p숫자만 콤마로 나열:",
                   max_new_tokens=90, temperature=0.0)
    return [m.group(1) for m in re.finditer(r"p(\d{1,4})", raw)][:top]


def keyword_set(question, parts_desc, titles_txt):
    """신호 시트 판독 결과를 거를 키워드 (질문의 한국어는 못 쓰므로 영문 근거에서 뽑는다)."""
    toks = set()
    for s in list(parts_desc) + list(titles_txt):
        for t in re.findall(r"[A-Z]{3,}", str(s).upper()):
            if t not in {"THE", "AND", "FOR", "CONTROL", "CIRCUIT", "TYPE", "SPEC", "OPTION"}:
                toks.add(t)
    return toks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", default=str(CACHE / "title_index.json"))
    ap.add_argument("--parts", default=str(CACHE / "parts_index2.json"))
    ap.add_argument("--render-dir", default=str(CACHE / "pages_400"))
    ap.add_argument("--scale", type=float, default=4.0, help="렌더 배율(4.0≈400DPI)")
    ap.add_argument("--func-pages", type=int, default=2, help="기능 시트 수")
    ap.add_argument("--sig-pages", type=int, default=2, help="신호 시트(INPUT SIGNAL 등) 수")
    ap.add_argument("--tmp", default=None)
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "results/puma_v3.json"))
    args = ap.parse_args()

    import glob
    pdf = glob.glob(str(ROOT / PDF_GLOB))[0]
    titles = json.loads(Path(args.titles).read_text(encoding="utf-8"))["pages"]
    parts = json.loads(Path(args.parts).read_text(encoding="utf-8"))["parts"]
    render_dir = Path(args.render_dir)
    tmp = Path(args.tmp) if args.tmp else Path(os.environ.get("TMPDIR", "/tmp")) / "puma_v3"
    tmp.mkdir(parents=True, exist_ok=True)

    code2page = defaultdict(set)
    for o in titles:
        for c in o.get("sheet_codes", []):
            code2page[c].add(str(o["page"]))
    sym = {p["symbol"]: p for p in parts}
    page_title = {str(o["page"]): o.get("title", "") for o in titles}

    llm = LLM(os.environ.get("LLM_NAME", "gemma4"), backend="vllm_api",
              api_base=os.environ.get("VLLM_API_BASE", "http://127.0.0.1:8001/v1"),
              api_model=os.environ.get("VLLM_API_MODEL", "gemma4"))
    qa = json.loads(GOLD.read_text(encoding="utf-8"))["qa_pairs"]
    if args.n:
        qa = qa[:args.n]
    log.info(f"v3: func={args.func_pages}, signal={args.sig_pages}, scale={args.scale}, n={len(qa)}")

    rows, recs = [], []
    t0 = time.time()
    for i, it in enumerate(qa):
        q = it["question"]; gaddr = it.get("key_addresses", [])
        # --- 트랙 1: 기능 시트 (부품 라우팅 + 제목) ---
        picked_parts = pick_parts(llm, q, parts)
        score = defaultdict(float)
        for r, s in enumerate(picked_parts):
            for c in sym.get(s, {}).get("sheets", []):
                for p in code2page.get(c, ()):
                    score[p] += 1.0 / (1 + r)
        for r, p in enumerate(pick_sheets(llm, q, titles, top=3)):
            score[p] += 1.5 / (1 + r)
        func_pages = [p for p, _ in sorted(score.items(), key=lambda kv: -kv[1])[:args.func_pages]]
        # --- 트랙 2: 신호 시트 (PLC 어드레스가 실제로 실리는 곳) ---
        sig_pages = pick_sheets(llm, q, titles, top=args.sig_pages, only=SIGNAL_SHEET,
                                label="PLC 입출력 신호 ")
        sig_pages = [p for p in sig_pages if p not in func_pages]

        kws = keyword_set(q, [sym.get(s, {}).get("description", "") for s in picked_parts],
                          [page_title.get(p, "") for p in func_pages])
        found = []
        for p in func_pages:                      # 기능 시트: 어드레스가 적으므로 전부 채택
            found += read_page(llm, render_page(pdf, p, render_dir, args.scale), tmp, p)
        for p in sig_pages:                       # 신호 시트: 라벨 적합성으로 필터
            for f in read_page(llm, render_page(pdf, p, render_dir, args.scale), tmp, p):
                lab = f["label"].upper()
                if not kws or any(k in lab for k in kws):
                    found.append(f)
        addrs = sorted({f["address"] for f in found})
        ev = "\n".join(f"{f['address']}  {f['label']}  (p{f['page']} {page_title.get(f['page'],'')})"
                       for f in found) or "(판독된 어드레스 없음)"
        ans = llm.chat(
            "CNC 전기회로 진단 전문가. 도면에서 판독한 근거만 사용하고 지어내지 않는다.",
            f"질문: {q}\n\n도면에서 판독한 근거(어드레스 / 라벨 / 시트):\n{ev}\n\n"
            f"관련 부품 태그: {', '.join(picked_parts) or '없음'}\n\n"
            f"점검 순서를 단계별로 제시하되 **PLC 어드레스와 부품 태그를 반드시 인용**하세요.",
            max_new_tokens=600, temperature=0.0)
        if addrs:
            ans += "\n\n[판독 어드레스] " + ", ".join(addrs)

        ar = addr_recall(ans, gaddr)
        if ar["recall"] is not None:
            recs.append(ar["recall"])
        rows.append({"id": it.get("id"), "question": q, "gold_addr": gaddr,
                     "gold_answer": it.get("answer", ""),
                     "picked_parts": picked_parts, "func_pages": func_pages,
                     "sig_pages": sig_pages,
                     "page_titles": [page_title.get(p, "") for p in func_pages + sig_pages],
                     "read_addrs": addrs, "answer": ans, "addr": ar})
        log.info(f"[{i+1}/{len(qa)}] {it.get('id')}: func p{func_pages} sig p{sig_pages} "
                 f"| 판독 {len(addrs)}개 | recall={ar['recall']} matched={ar.get('matched')}")

    n = len(rows)
    avg_prop = sum(len(r["read_addrs"]) for r in rows) / max(1, n)
    tot_g = sum(len(r["gold_addr"]) for r in rows)
    tot_h = sum(len(r["addr"].get("matched") or []) for r in rows)
    summary = {"n": n, "addr_recall_pct": round(100*sum(recs)/len(recs), 1) if recs else None,
               "micro_recall_pct": round(100*tot_h/max(1, tot_g), 1),
               "avg_proposed_addrs": round(avg_prop, 1),
               "efficiency_per_1000": round(1000*tot_h/max(1, sum(len(r["read_addrs"]) for r in rows)), 1),
               "func_pages": args.func_pages, "sig_pages": args.sig_pages, "scale": args.scale,
               "elapsed_sec": round(time.time()-t0, 1),
               "note": "도면 참조체계 라우팅 + 신호시트 트랙 + 400DPI region 판독(누출 없는 프롬프트)"}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows},
                                         ensure_ascii=False, indent=2, default=str))
    log.info(f"wrote {args.out}")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
