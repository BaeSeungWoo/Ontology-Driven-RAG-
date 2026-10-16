"""PUMA v13 — **강제 인용 범위 확대**로 생성 단계 손실을 없앤 구성 (채택).

v12까지의 병목을 문항 단위로 재측정한 결과(P71):
  · 인덱스는 gold 34개를 **100% 담고 있다** (근거풀에 못 든 11개도 전부 사전에는 존재)
  · 근거풀(생성기에 준 16줄)에 gold가 **23/34 = 67.6%** 들어간다
  · 그런데 답변은 17/34 = 50.0%만 인용한다 → **생성 단계에서 6개 손실**
  · 더 파보니 강제 인용 규칙(상위 5)은 **100% 지켜지고 있었다**(상위 5칸 gold 15 → 15 인용).
    손실은 전부 **강제하지 않은 6~16위 구간**에서 났다.

그래서 강제 범위를 상위 5 → **상위 12**로 넓히고 생성 토큰을 1200으로 올렸다.
결과: 생성 손실 6 → **0**, recall 50.0 → **67.6%**, 완전일치 4 → **6/11**,
부품 언급 49.2 → **56.5%**, ≥1적중 **11/11**. 근거 밖 어드레스 인용은 **0%**.
대가는 precision(27.4 → 17.3%, 인용 5.6 → 12.1개)이라 **v11이 여전히 F1 최적**(0.400)이다.

같은 스크립트로 시도했다가 기각한 것(전부 --flag로 남겨 둠):
  · `--norm-labels`  라벨 중복 제거 → recall 44.1% ❌ (lab_cover가 올라 감점 대상 증가)
  · `--must-top 8`   중간값        → recall 55.9%, 완전일치 3/11 ❌
  · `--sig-pick 10`  신호 예산 확대 → 근거풀 67.6 → 58.8% ❌ (신호 선택 희석, P19 재발)
  · `--page-prior 2` 1순위 시트 가산 → 근거풀 64.7%, recall 61.8% ❌
    (v7이 인터록 강제와 함께 롤백해 격리 검증이 없었는데, **page_prior 자체가 해롭다**)

  LLM_NAME=gemma4 VLLM_API_BASE=http://127.0.0.1:8001/v1 \
  python scripts/run_puma_v13.py --evidence-top 16 --quota --devices \
      --io-rows cache_puma/io_index_rows_merged.json --out results/puma_v13.json
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from puma_read import (render_page, read_crops, merge_by_address, read_devices,
                       DEVICE_SYS_TMPL)
from puma_evidence import (label_confidence, rank_evidence, rank_evidence_quota,
                           format_evidence, is_uncertain, _display_labels)
from parts_select import pick_parts, pick_sheets, _relevance
from metrics import addr_recall
from llm import LLM
from llm import get_logger
from ko_terms import SUBSYS, SUBSYS_KO
from ko_terms import question_axes
from runtime_support import report_progress
from electrical.grounding import CIRCUIT_RULES

log = get_logger("puma_v13")
GOLD = ROOT / "data/example_qa_pair/gold_qa_pairs.json"
CACHE = ROOT / "cache_puma"
ADDR_NORM = re.compile(r"([XYRGFKT])0*(\d+)\.(\d)")


_NORM_SUB = r"\1\2.\3"


def _lev1(a: str, b: str) -> bool:
    """편집거리가 정확히 1 인가(치환·삽입·삭제 한 번)."""
    if a == b:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) == 1
    if len(a) > len(b):
        a, b = b, a
    if len(b) - len(a) != 1:
        return False
    i = 0
    while i < len(a) and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def norm(a):
    """앞자리 0 정규화. 치환 템플릿이 점을 리터럴로 넣으므로, 점 없는 어드레스 체계
    (MAZAK `X08A` · DECKEL `I05`)에서는 --addr-norm-sub 로 바꿔야 한다."""
    return ADDR_NORM.sub(_NORM_SUB, str(a).strip().upper())


def _index_sig(path):
    """인덱스 파일의 지문 — 크기와 항목 수. 내용이 바뀌면 재개를 취소하기 위한 것."""
    try:
        p = Path(path)
        if not p.exists():
            return ""
        d = json.loads(p.read_text(encoding="utf-8"))
        n = d.get("n") or d.get("n_symbols") or len(d.get("entries", d) or [])
        return f"{p.stat().st_size}:{n}"
    except Exception:
        return ""


GENERIC_SYS = (
    "You are given the PLC signal names of ONE industrial machine's electrical drawing. "
    "Mark which ones are MACHINE-GLOBAL status signals — they describe the state of the whole "
    "machine (machine activated, emergency stop chain, stop switches, mode selection, general "
    "ready/alarm lamps) and are therefore relevant to almost ANY fault question.\n"
    "Everything tied to ONE subsystem (coolant, hydraulic, lubrication, spindle, chip conveyor, "
    "tool clamp, door, axis) is NOT machine-global.\n"
    "Each line is `NAME<TAB>label(s)` when labels are known — judge by the LABEL, not by "
    "the name: a name containing ALARM/MALFUNCTION/ERROR/STATE is NOT global if its label "
    "names one subsystem (e.g. `IX_CU_MALFUNCT_N` labelled 'Coolant Unit malfunction' is "
    "coolant-only). When no label is given, judge by the name alone.\n"
    'Answer ONLY JSON: {"global": [names copied exactly, WITHOUT the label part]}.')


def generic_signals(llm, addrs, cache_path, labels=None):
    """**질문과 무관하게 매번 이기는 신호**를 한 번 골라 둔다.

    심사에서 가장 크게 지적된 결함이다 — DMU85 10문항 중 7개가
    `IX_MACHINE_ACTIVAT`·`IX_ESTP_CH1_N`·`IX_STOP_SWITCH_1~3`으로 시작하고,
    SL2500 8개가 `-KA020/21/22`·`Y6.0`으로 끝난다. 이건 답이 아니라 검색 아티팩트다.
    통계로는 못 가른다(모든 문항에 나오는 것이 곧 '중요한 것'일 수도 있다) —
    **무엇이 기계 전역 상태인지**는 도면을 아는 쪽이 판단해야 하므로 모델에게 시킨다.
    문서당 한 번만 부르고 캐시한다."""
    p = Path(cache_path)
    if p.exists():
        try:
            return set(json.loads(p.read_text(encoding="utf-8"))["global"])
        except Exception:
            pass
    names = sorted({a for a in addrs})[:400]
    # ⚠ **라벨을 함께 준다.** 어드레스 이름만 주면 벤더 표기에 따라 기능이 켜지거나 꺼진다
    #   (실측: SL2500 은 `X0.0`·`Y2.1` 라 이름에 의미가 없어 분류 결과 **0개** →
    #   `--demote-generic` 무효. DMU85 는 `IX_GEN_*` 라 분류는 되지만 "MALFUNCT/ALARM"
    #   이름만 보고 `IX_CU_MALFUNCT_N`(Coolant Unit **한정**)까지 넣어 39개로 과분류,
    #   codex 는 5개). 라벨에 계통이 적혀 있으므로 그걸 보면 양쪽이 고쳐진다.
    #   labels 가 없으면 기존 동작 그대로 — 이름만 보낸다.
    def _line(a):
        ls = [str(x) for x in (labels or {}).get(a, [])][:2]
        return f"{a}\t{' | '.join(ls)}" if ls else str(a)
    got = set()
    for i in range(0, len(names), 120):
        try:
            raw = llm.chat(GENERIC_SYS, "\n".join(_line(a) for a in names[i:i + 120]),
                           max_new_tokens=500, temperature=0.0)
            m = re.search(r"\{.*\}", str(raw), re.S)
            if m:
                got |= {str(x) for x in (json.loads(m.group(0)).get("global") or [])}
        except Exception:
            pass
    got &= set(names)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"global": sorted(got)}, ensure_ascii=False, indent=1), encoding="utf-8")
    log.info(f"기계 전역 신호 {len(got)}개 (예: {sorted(got)[:4]})")
    return got


# 한 글자 계통어(문·축·칩·척)는 **조사가 붙었을 때만** 인정한다. 단순 부분문자열로 보면
# "뭐가 **문**제인가요"의 `문`이 도어로 잡혀 엉뚱한 계통이 면제된다(실측).
_JOSA = "이가은는을를의도만에와과로으서부터까지"


def _has_ko(q, w):
    if len(w) > 1:
        return w in q
    for m in re.finditer(re.escape(w), q):
        nxt = q[m.end():m.end() + 1]
        if nxt == "" or nxt in _JOSA or not ("\uac00" <= nxt <= "\ud7a3"):
            return True
    return False


def question_subsys(q):
    """한국어 질문 → 계통 정규식들. `ko_terms` 표를 그대로 쓴다(두 곳에 복사하면 갈라진다)."""
    return [re.compile(rx) for key, _ko, rx, *_ in SUBSYS
            if any(_has_ko(q, w) for w in SUBSYS_KO.get(key, ()))]


def demote_generic(ranked, generic, qrx, factor=0.35):
    """전역 신호는 **질문이 그 계통을 묻지 않는 한** 점수를 깎아 뒤로 민다.

    지우지는 않는다 — 비상정지가 진짜 원인인 문항도 있다(dmu85-sym-003).

    ⚠ 면제 기준을 처음에는 `kws`(선택된 신호·부품 어휘)로 잡았는데 **한 번도 강등이
    안 일어났다**. `kws` 는 같은 문서에서 온 어휘라 `MACHINE`·`CONTROL` 같은 흔한 낱말이
    거의 항상 들어 있어 면제가 늘 성립했다. 질문에서 직접 계통을 뽑아야 한다 —
    "비상정지 버튼을 풀었는데"→`emg`→`EMERGENCY|SAFETY RELAY|INTERLOCK` 이 라벨에 걸리므로
    그 문항에서는 면제되고, "절삭유가 안 나와요"→`coolant` 에서는 걸리지 않아 강등된다."""
    if not generic:
        return ranked
    out, moved = [], 0
    for sc, kw, a, e in ranked:
        if a in generic:
            lab = " ".join([str(a)] + [str(x) for x in (e.get("labels") or [])]).upper()
            if not any(r.search(lab) for r in qrx):
                sc = sc * factor
                moved += 1
        out.append((sc, kw, a, e))
    out.sort(key=lambda t: -t[0])
    if moved:
        log.info(f"    전역 신호 {moved}개 강등")
    return out


def io_direction(addr, out_re=None, in_re=None):
    """어드레스가 **입력인지 출력인지**. 접두어로 판정한다.

    FANUC X=입력 Y=출력 · Siemens I=입력 Q=출력 · DMG IX_/ISX_=입력 OX_/OSX_=출력.
    `R`·`M` 같은 내부 릴레이는 방향이 없으므로 빈 문자열."""
    a = str(addr).upper()
    if (out_re or _OUT_ADDR).match(a):
        return "출력"
    if (in_re or _IN_ADDR).match(a):
        return "입력"
    return ""


_OUT_ADDR = re.compile(r"^(?:Y|Q|OS?X_)")
_IN_ADDR = re.compile(r"^(?:X|I(?:S?X_)?)")


def load_io_dict(path):
    """어드레스 → 후보 라벨 / 라벨 → 어드레스 / 어드레스 → 합의 신뢰도.

    병합 인덱스(`merge_io_index.py`)는 밴드 설정이 다른 두 판독의 **합의 여부**를
    confidence(high/medium/low)로 준다. 합의한 라벨은 gold 판정 가능분에서 3/3 정답이었고,
    불일치(low)는 후보를 병기해야 한다(9개 중 6개는 후보 안에 정답이 있음)."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    a2l, l2a, a2c = {}, defaultdict(set), {}
    for e in d["entries"]:
        a = norm(e["address"])
        labs = [x for x in e.get("labels", []) if x]
        a2c[a] = e.get("confidence", "medium")
        if labs:
            a2l.setdefault(a, [])
            for l in labs:
                if l not in a2l[a]:
                    a2l[a].append(l)
                l2a[l.upper()].add((a, e.get("page", "")))
    return a2l, l2a, a2c


def pick_signals(llm, question, names, top=6):
    raw = llm.chat("CNC 회로도 진단 전문가. 목록에 있는 신호명만 사용.",
                   f"질문: {question}\n\n신호명 목록:\n{', '.join(sorted(names))}\n\n"
                   f"이 고장 진단에 확인해야 할 신호를 관련도 순으로 최대 {top}개, "
                   f"신호명만 콤마로 나열:", max_new_tokens=140, temperature=0.0)
    up = {n.upper(): n for n in names}
    out = []
    for tok in re.split(r"[,\n]", raw):
        t = tok.strip().upper()
        if not t or t == "없음":
            continue
        if t in up:
            out.append(up[t]); continue
        for n in names:                                  # 부분 일치(단어 경계)
            if len(t) >= 4 and re.search(r"(?<![A-Z0-9])" + re.escape(t) + r"(?![A-Z0-9])", n.upper()):
                out.append(n); break
    seen, uniq = set(), []
    for n in out:
        if n not in seen:
            seen.add(n); uniq.append(n)
    return uniq[:top]


def lexical_signals(question, names, l2a, top=6):
    """**LLM 없이** 질문어–이름 매칭 점수로 신호를 고른다(P135).

    A~D 네 실행에서 드러난 것: 카탈로그를 깨끗하게 해도(P134) 인덱스를 정확하게 해도(P132)
    recall이 안 움직인다. 매번 흔들리는 곳은 `pick_signals` 한 번의 LLM 판단이다
    (같은 설정 재실행에서도 ±1개). 그렇다면 그 판단을 **결정적인 점수**로 바꿔 본다.

    두 축을 쓴다 — 계통(`터렛`→`TURRET|ATC|INDEX`)과 동작(`다음 번호로 안 돌아가`→
    `INDEX|DECODE`·`ROTAT`). 계통 하나로는 못 가른다: 터렛 문항에서 `TURRET`이 들어간
    이름이 43~61개라 6칸을 무작위로 채우는 것과 같다."""
    subs, acts = question_axes(question)
    if not subs and not acts:
        return []                                  # 축이 없으면 포기 — LLM으로 넘긴다
    qu = question.upper()
    scored = []
    for n in names:
        core = re.sub(r"\s*\(?\d{5}\s*/\s*\d\)?\s*", " ", n).strip().upper()
        core = re.sub(r"\s{2,}", " ", core)
        sc = 0.0
        if len(core) >= 5 and core in qu:
            sc += 6.0                              # 질문에 그대로 인쇄된 이름
        sc += 3.0 * sum(1 for rx in subs if rx.search(core))
        sc += 1.5 * sum(1 for rx in acts if rx.search(core))
        if sc <= 0:
            continue
        fan = len(l2a.get(n.upper(), ()))
        if 1 <= fan <= 2:
            sc += 0.5                              # 어드레스가 적은 = 구체적인 이름 우대
        sc -= 0.002 * len(core)                    # 동점이면 짧은 쪽 (군더더기 없는 이름)
        scored.append((sc, n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _, n in scored[:top]]



EXPAND_SYS = (
    "You are given a Korean maintenance complaint about a CNC machine, and you must guess the "
    "ENGLISH words that the machine's ELECTRICAL DRAWING would print for the circuits involved. "
    "Drawing labels are terse uppercase engineering English: 'COOLANT PUMP MOTOR ON', "
    "'LUBRICATION PRESSURE CHECK', 'CHUCK CLAMP/UNCLAMP FOOT SWITCH', 'AUTO DOOR OPEN'. "
    "List the words and short phrases that would appear on the relevant sheets — the subsystem, "
    "the actuator, the sensor, the alarm, and the usual synonyms. "
    "Output ONLY a JSON array of 8-16 uppercase strings. No explanation.")


def expand_query(llm, question, cache=None):
    """질문 → **도면 영어 어휘**. 신호 선택보다 먼저 온다.

    지금 구조는 이름 553개를 통째로 보여 주고 6개를 고르라고 한다 — 주의가 희석되고,
    실측상 LLM의 gold 도달은 18/34에서 멈춘다. 그런데 **카탈로그에 이름이 있는 gold는
    32/34**다(P135). 즉 헤드룸은 '고르기'가 아니라 '후보를 좁히기'에 있다.

    한국어 증상어와 도면 영어 사이를 잇는 것이 병목이므로(`사이클 스타트`는 계통표에 없고
    `X11.4`의 이름은 `(SM1)`뿐이다), 그 연결만 LLM에게 먼저 시키고 매칭은 결정적으로 한다.
    키워드 표(`ko_terms`)로는 8/34까지밖에 못 갔다 — 이건 어휘가 아니라 의미의 문제다."""
    if cache is not None and question in cache:
        return cache[question]
    try:
        raw = llm.chat(EXPAND_SYS, f"불만: {question}\n\nJSON 배열만:",
                       max_new_tokens=260, temperature=0.0)
    except Exception as e:
        log.warning(f"질의 확장 실패(무시): {e}")
        return []
    m = re.search(r"\[.*\]", raw, re.S)
    out = []
    if m:
        try:
            out = [str(t).strip().upper() for t in json.loads(m.group(0)) if str(t).strip()]
        except Exception:
            out = []
    if not out:                                   # 배열이 안 나오면 대문자 토막이라도 건진다
        out = [t.strip() for t in re.findall(r"[A-Z][A-Z /&.\-]{3,}", raw)]
    out = [t for t in dict.fromkeys(out) if 3 <= len(t) <= 40]
    if cache is not None:
        cache[question] = out
    return out


def _content_tokens(text):
    """도면 이름의 내용어. 거의 모든 이름에 붙는 말은 뺀다 — 변별력이 없다."""
    return [t for t in re.findall(r"[A-Z]{3,}", str(text).upper())
            if t not in _STOP]


_STOP = {"THE", "AND", "FOR", "WITH", "CHECK", "SIGNAL", "UNIT", "SYSTEM", "MODE", "STATE"}


def shortlist_by_terms(terms, names, keep, idf=None):
    """확장어로 카탈로그를 좁힌다. **부분문자열이 아니라 토큰 겹침**으로 잰다.

    부분문자열 매칭은 `LUBE PRESSURE SWITCH`(확장어)가 `LUBRICATION PRESSURE CHECK`(도면)에
    안 걸린다 — 실측상 그렇게 하면 gold 도달이 18→19로 +1에 그치고 바로 포화했다.
    내용어를 IDF로 가중해 겹치면 **18→22**(상위 10) · **23**(20) · **25**(40)가 된다.

    긴 이름은 우연히 겹칠 확률이 높으므로 길이로 약간 감점한다."""
    if not terms:
        return []
    q = set()
    for t in terms:
        q |= set(_content_tokens(t))
    if not q:
        return []
    if idf is None:
        idf = {}
    scored = []
    for n in names:
        ws = set(_content_tokens(n))
        sc = sum(idf.get(w, 1.0) for w in ws & q)
        if sc > 0:
            scored.append((sc / (1 + 0.3 * len(ws)), n))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [n for _, n in scored[:keep]]


def build_idf(names):
    """이름 카탈로그의 역문서빈도. 흔한 단어(`MOTOR`)보다 드문 단어(`PATROL`)를 믿는다."""
    df = Counter()
    for n in names:
        df.update(set(_content_tokens(n)))
    N = max(len(names), 1)
    return {t: math.log(1 + N / (1 + c)) for t, c in df.items()}


def rerank_llm(llm, question, ranked, conf, page_title, keep, adaptive=False):
    """**LLM 근거 재순위** — 점수식이 못 하는 의미 판단을 한 번의 호출로 맡긴다.

    왜 필요한가(측정):
      · gold가 근거 1~11위에 흩어져 있고 상위 5위 안에는 15/23뿐이다. 그래서 강제 인용 범위를
        12로 넓혀야 했고(recall 50→67.6%) 그 대가로 정밀도가 27.4→17.3%로 떨어졌다.
      · 후보를 넓히면(v14) 점수식이 좋고 나쁨을 구별 못 해 **근거풀이 오히려 나빠졌다**
        (67.6→58.8%). 즉 넓히기가 위험한 이유는 넓이가 아니라 **선별기의 부재**였다.
    그래서 폭은 넓히되(pool) 의미를 읽는 재순위를 붙여 상위를 정예화한다.
    파싱 실패 시 원래 점수 순서를 그대로 쓴다(안전한 폴백)."""
    if len(ranked) <= keep:
        return ranked
    lines = []
    for i, (s, kw, a, e) in enumerate(ranked, 1):
        scored = conf.get(a, {})
        labs = _display_labels(scored)
        nm = labs[0][0] if labs else "(이름 판독 실패)"
        pg = str(e.get("page", ""))
        lines.append(f"{i}. {a} — {nm} (p{pg} {page_title.get(pg,'')})")
    raw = llm.chat(
        "CNC 전기회로 진단 전문가. 주어진 후보 중에서만 고른다.",
        f"질문: {question}\n\n"
        f"아래는 이 고장과 관련될 수 있는 PLC 어드레스 후보다.\n" + "\n".join(lines) +
        f"\n\n이 고장을 진단할 때 **실제로 확인해야 할 순서대로** 번호만 "
        f"콤마로 나열하라(최대 {keep}개). 관련 없는 것은 빼라. 번호만 출력.",
        max_new_tokens=120, temperature=0.0)
    order, seen = [], set()
    for m in re.finditer(r"\d+", raw):
        i = int(m.group(0)) - 1
        if 0 <= i < len(ranked) and i not in seen:
            seen.add(i); order.append(ranked[i])
        if len(order) >= keep:
            break
    if not order:
        return ranked[:keep]
    if adaptive:
        # **적응적 개수** — LLM이 "관련 없는 것은 빼라"에 따라 고른 개수를 그대로 쓴다.
        # 고정 개수로 자르면 gold가 8개인 cycle-start는 부족하고, 1개인 에어는 과잉이다.
        # 문항 난이도에 따라 근거 폭이 달라지게 둔다(최대 keep까지만).
        return order[:keep]
    for item in ranked:                      # 모자라면 점수 순으로 채운다
        if len(order) >= keep:
            break
        if item not in order:
            order.append(item)
    return order[:keep]


def build_addr2page(io_path, signal_path, page_index_path, chunks_df, rows_path=None):
    """어드레스 → 그 어드레스가 실린 시트들 (역라우팅 재료).

    `page_index.json`은 전면 OCR 산출물이라 신규 문서용으로 다시 만들지 않는다
    (이 레포가 열거 환각으로 기록했고 qwen 때도 재구축을 거부했다). 없으면 건너뛰고,
    대신 `rows_path`(행 단위 인덱스)로 역라우팅 신호를 복원한다 — 이쪽은 신뢰하는 인덱스다."""
    a2p = defaultdict(set)
    for p in (io_path, signal_path):
        if p and Path(p).exists():
            for e in json.loads(Path(p).read_text(encoding="utf-8"))["entries"]:
                a2p[norm(e["address"])].add(str(e["page"]))
    if page_index_path and Path(page_index_path).exists():
        from puma_retrieval import LookupIndex
        idx = LookupIndex(json.loads(Path(page_index_path).read_text(encoding="utf-8"))["entries"],
                          chunks_df, max_addr_per_signal=3)
        for pg, aa in idx.page_addrs.items():
            for a in aa:
                a2p[a].add(str(pg))
    if rows_path and Path(rows_path).exists():
        for e in json.loads(Path(rows_path).read_text(encoding="utf-8"))["entries"]:
            a2p[norm(e["address"])].add(str(e["page"]))
    return a2p


def collect_signal_hits(names, l2a, a2l):
    """라운드로빈 후보에 신호 선택 순위를 보존한다. 판독 예산은 호출부에서 적용한다."""
    by_sig = [(rank, nm, sorted(l2a.get(nm.upper(), ())))
              for rank, nm in enumerate(names) if 0 < len(l2a.get(nm.upper(), ())) <= 4]
    first_rank = {}
    for rank, _, addrs in by_sig:
        for address, _ in addrs:
            first_rank.setdefault(address, rank)
    hits, seen = [], set()
    for depth in range(4):
        for rank, nm, addrs in by_sig:
            if depth < len(addrs):
                address, page = addrs[depth]
                if address not in seen:
                    seen.add(address)
                    hits.append({"address": address, "labels": a2l.get(address, [nm]),
                                 "page": page, "src": "I/O MAP", "signal_rank": first_rank[address]})
    return hits


def signal_circuit_pages(hits, a2sheet, parts, code2page, explain):
    """명시된 시트 참조와 정확히 일치하는 부품 태그의 회로 시트만 연결한다."""
    by_tag = {str(p["symbol"]).upper().lstrip("-"): p for p in parts}
    routes = {}
    for hit in hits:
        address = norm(hit["address"])
        pages = set(a2sheet.get(address, ()))
        labels = list(hit.get("labels") or []) + [explain.get(address, {}).get("tag", "")]
        for label in labels:
            part = by_tag.get(str(label).strip().upper().lstrip("-"), {})
            for code in part.get("sheets", []):
                pages.update(code2page.get(code, ()))
        routes[address] = sorted({str(p) for p in pages}, key=int)
    return routes


def score_signal_pages(hits, a2sheet, page_title, io_page_route=0.0,
                       generic=(), qrx=(), demote_factor=1.0):
    score, refs = defaultdict(float), []
    for hit in hits:
        rank = hit["signal_rank"]
        weight = 3.0
        if norm(hit["address"]) in generic:
            label = " ".join([str(hit["address"])] + list(hit.get("labels") or [])).upper()
            if not any(rx.search(label) for rx in qrx):
                weight *= demote_factor
        page = str(hit.get("page", ""))
        if io_page_route and page and not re.search(
                r"\b(?:MAP|LIST)\b|terminal (?:diagram|location)", page_title.get(page, ""), re.I):
            score[page] += io_page_route / (1 + rank)
        for target in a2sheet.get(norm(hit["address"]), ()):
            score[target] += weight / (1 + rank)
            refs.append({"address": hit["address"], "from_page": hit.get("page"),
                         "page": target, "title": page_title.get(target, ""),
                         "w": round(weight / (1 + rank), 3)})
    return score, refs


def reverse_signal_pages(hits, a2p, circuit_pages, func_pages, limit, fallback=False):
    candidates = {}
    for hit in hits:
        pages = {str(p) for p in a2p.get(norm(hit["address"]), ()) if str(p) != str(hit["page"])}
        pages.update(circuit_pages.get(norm(hit["address"]), ()))
        if fallback and hit.get("page"):
            pages.add(str(hit["page"]))
        for page in pages - set(func_pages):
            # 여러 후순위 신호의 합산이 앞선 신호의 연결 회로를 밀어내지 않게 한다.
            candidates[page] = max(candidates.get(page, 0.0), 1.0 / (1 + hit["signal_rank"]))
    pages = [p for p, _ in sorted(candidates.items(), key=lambda kv: (-kv[1], int(kv[0])))[:limit]]
    return pages, candidates


# `--prioritize` (P271 블라인드 심사): 쪽 전체 기기를 보여 주자 답이 20~30개 점검 목록이 되어
# 4~6단계 원인 체인이 묻혔다(Q5: 무관 태그 24개). 무관 신호를 "관련 없음" 절로 뺀 답이 이겼다.
_PRIO_RULE = ("\n8) **본문은 이 고장의 원인 체인만** 4~8단계로 쓰세요(지령 → 릴레이/모듈 → 접촉기 → "
              "보호기 → 모터/부하 → 배선). 근거에 있지만 이 고장의 직접 원인이 아닌 기기·신호는 "
              "본문에 섞지 말고 맨 끝 **[참고 — 같은 도면의 관련 기기]** 절에 태그와 한 줄 설명으로만 "
              "나열하세요. 타워램프·전역 준비 신호처럼 모든 고장에 공통인 항목은 참고 절에도 넣지 마세요.")
# `--feasible` (P290 심사): NC 화면이 꺼진 고장에서 "진단 화면에서 Y5.3 확인"을 지시했다.
_FEAS_RULE = ("\n9) **지시한 점검은 질문의 고장 상태에서 실제로 할 수 있어야 합니다.** 화면·제어전원·"
              "통신이 죽은 고장이면 진단 화면 확인을 지시하지 말고 전원 버튼·차단기·퓨즈·램프·커넥터 등 "
              "**물리 점검**을 먼저 쓰세요.")
_COIL_RULE = ("\n10) 접촉기·릴레이를 쓸 때 [코일 급전·직렬 접점] 기록이 있으면 **코일이 어디서 전원을 받고 "
              "어떤 접점(보호기 보조접점 13-14, 비상정지·도어 접점 등)을 직렬로 거치는지** 그 단계에 쓰세요. "
              "PLC 출력 없이 직접 급전되는 코일이면 그렇다고 쓰세요. [골라진 부품의 시트를 가리키는 I/O 신호]가 "
              "있으면 그 접촉기·밸브를 **실제로 구동하는 명령 신호**는 거기서 고르세요. [회로도에서 이 신호가 "
              "실제로 연결된 기기]가 I/O 맵·설명 사전의 태그와 다르면 **회로도 기록을 따르세요**(릴레이 없이 "
              "직접 구동이면 그렇게 쓰세요).")
_BTN_RULE = ("\n11) 전원 투입·비상정지 해제·리셋처럼 **사람이 버튼을 눌러야 회로가 사는** 고장이면, 회로도 기록에서 "
             "그 버튼(전원 ON·M/C READY·Machine ON 등)과 자기유지 접점을 찾아 **어떤 버튼을 누르고 무엇이 "
             "자기유지되는지** 쓰세요. 전원이 죽어 화면을 볼 수 없으면 진단 화면 대신 물리 점검을 지시하세요.")
_POL_RULE = ("\n12) 신호명·접점 번호에서 정상 입력값을 추론하지 마세요. "
             "극성과 운전 상태의 관계는 출처에 명시된 범위만 설명하고, 없으면 PLC 래더·동작 조건 확인이 필요하다고 쓰세요.")
_POL2_RULE = _POL_RULE
# `--feed-source-rule`(P359): v49 DMU85 쿨러 — [급전원] 블록에 "-B6-01Q21 outlet 4 → 쿨러" 가 들어갔는데도
# 답은 냉각 유닛(-A1-14Q51) 계통으로 새고 급전 보호기기를 안 썼다.
_FEED_RULE = ("\n13) 근거에 **[급전원]** 블록이 있으면, 고장난 부하로 이어지는 전위선의 **보호기기(차단기·모터보호스위치)와 "
              "출력 단자**를 '전원 공급' 단계에 쓰세요. 이름이 비슷한 다른 장치(예: 냉각 유닛 vs 전장함 쿨러)의 급전 계통과 "
              "섞지 마세요.")
# `--full-names` (P256 gold 대조): 신호명 축약·정격/모델 누락이 DMU85 의 진짜 손실이었다.
_FULL_RULE = ("\n7) **이름은 근거 표기 그대로 전부 쓰세요.** 신호명·태그를 줄이거나 슬래시로 "
              "묶지 마세요(`ISX_A_CH1_LKD`, `ISX_A_CH2_LKD` 를 `IX_A_CH1/CH2_LKD` 로 쓰지 말 것). "
              "부품을 쓸 때는 목록 설명에 있는 **모델명·정격([...] 안, A·V·kW 값)**을 괄호로 함께 쓰세요.")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--titles", default=str(CACHE / "title_index.json"))
    ap.add_argument("--parts", default=str(CACHE / "parts_index2.json"))
    ap.add_argument("--io", default=str(CACHE / "io_index_merged.json"))
    ap.add_argument("--io-rows", default=str(CACHE / "io_index_rows.json"),
                    help="행 단위 판독 인덱스(라벨 보강 + 시트 참조 라우팅)")
    ap.add_argument("--ref-index", default="",
                    help="시트참조 전용 인덱스(비우면 --io-rows에서 가져옴). "
                         "합의 필터를 건 인덱스를 여기에 물리면 **라벨은 그대로 두고 "
                         "라우팅 키만** 교체해 격리 검증할 수 있다")
    ap.add_argument("--evidence-top", type=int, default=16, help="생성기에 줄 상위 근거 수")
    ap.add_argument("--quota", action="store_true", help="출처별 쿼터로 근거 선택(IO/DWG 균형)")
    ap.add_argument("--signals", default=str(CACHE / "signal_index.json"))
    ap.add_argument("--render-dir", default=str(CACHE / "pages_400"))
    ap.add_argument("--scale", type=float, default=4.0)
    ap.add_argument("--func-pages", type=int, default=2)
    ap.add_argument("--rev-pages", type=int, default=2, help="역라우팅으로 추가 판독할 시트 수")
    ap.add_argument("--sig-top", type=int, default=8)
    ap.add_argument("--sig-pick", type=int, default=6,
                    help="LLM에게 고르게 할 신호 개수. IO 트랙은 여기서 고른 신호로만 "
                         "어드레스를 만들므로, 정답 신호가 안 뽑히면 그 어드레스는 근거에 못 든다")
    ap.add_argument("--dev-named", action="store_true", default=False,
                    help="회로도 부품 태그 중 **기능 텍스트가 함께 읽힌 것만** 제시")
    ap.add_argument("--rerank", action="store_true", default=False,
                    help="근거를 LLM으로 재순위(호출 1회). 폭을 넓혀도 안전해진다")
    ap.add_argument("--rerank-adaptive", action="store_true", default=False,
                    help="재순위가 고른 개수를 그대로 사용(부족해도 점수순으로 안 채움)")
    ap.add_argument("--show-top", type=int, default=0,
                    help="재순위 후 생성기에 실제로 줄 근거 수(0=--evidence-top 그대로)")
    ap.add_argument("--dedup-names", action="store_true", default=False,
                    help="신호 선택 목록에서 시트참조 유무 중복을 제거(순위 계산은 불변)")
    ap.add_argument("--q-match", action="store_true", default=True,
                    help="질문에 그대로 등장하는 사전 이름을 신호 선택 앞에 강제 삽입(결정적). "
                         "'CYCLE START 버튼 눌러도…' 질문에서 사전의 CYCLE START(X33.6)를 "
                         "LLM이 고르지 않은 사례에 대응. **기본 켜짐** — 격리 검증에서 "
                         "recall 67.6 → 70.6%%, 정밀도도 17.3 → 18.0%%로 동반 상승")
    ap.add_argument("--no-q-match", dest="q_match", action="store_false")
    ap.add_argument("--tmp", default=None)
    ap.add_argument("--n", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "results/puma_v25.json"))
    ap.add_argument("--norm-labels", action="store_true", default=False,
                    help="후보 라벨에서 시트참조를 떼고 중복 제거. **기본 꺼짐** — "
                         "불확실률은 93→81%%로 내려가지만 lab_cover가 올라 반복라벨 감점 대상이 "
                         "늘고 gold가 근거 밖으로 밀린다(v13a: recall 50.0→44.1%%)")
    ap.add_argument("--no-norm-labels", dest="norm_labels", action="store_false")
    ap.add_argument("--page-prior", type=float, default=0.0,
                    help="라우팅 점수가 높은 시트에서 읽힌 근거에 주는 가산(0=끔). "
                         "v7이 인터록 강제와 함께 넣었다가 롤백돼 단독 검증이 없었다")
    ap.add_argument("--cat-relevance", action="store_true", default=False,
                    help="카탈로그가 상한을 넘을 때 **질문 적합도** 순으로 남긴다. "
                         "기본(꺼짐)은 짧은 항목부터 — 후보 수는 최대지만 질문과의 관련성은 "
                         "안 본다(실측: PUMA 24개·DMU 29개가 이 규칙으로 잘렸다)")
    ap.add_argument("--answer-continue", action="store_true", default=False,
                    help="답변이 토큰 상한에서 잘리면 한 번 이어쓴다. 지금까지는 "
                         "finish_reason 을 안 봐서 문장 중간에 끊긴 답이 그대로 채점됐다")
    ap.add_argument("--rev-fallback", action="store_true", default=False,
                    help="[기각됨 — 재현용으로만 남긴다] 역라우팅 후보가 없으면 "
                         "시트참조 **및 출처 페이지**로 되살린다. 절제에서 이것을 빼면 "
                         "키워드가 +6.5pp 회복됐다(잡음 바닥 2.6pp 밖). 출처 페이지가 "
                         "인덱스를 뽑아낸 배치표라서, 이미 요약된 표를 VLM 이 재판독하며 "
                         "판독 예산 2쪽을 쓰고 회로 증거를 밀어냈다. 대신 --rev-xref 를 쓴다")
    ap.add_argument("--route-demote-generic", action="store_true", default=False,
                    help="전역 신호의 **상호참조 라우팅 가중치**를 깎는다(기본 3.0 → "
                         "--route-demote-factor 배). `--demote-generic` 은 근거 순위만 "
                         "손보므로 라우팅에서는 전역 신호가 여전히 예산을 독식한다 "
                         "(실측: dmu85-sym-002 에서 6쪽 중 4칸). 면제 기준은 "
                         "demote_generic 과 같다 — 질문이 그 계통을 물으면 깎지 않는다")
    ap.add_argument("--route-demote-factor", type=float, default=0.35,
                    help="--route-demote-generic 의 감쇠 배수. demote_generic 기본값과 같다")
    ap.add_argument("--rev-xref", action="store_true", default=False,
                    help="역라우팅 후보가 없으면 **시트참조가 가리키는 회로 시트만** "
                         "되살린다(출처 페이지는 넣지 않는다). --rev-fallback 의 두 갈래 중 "
                         "해로웠던 쪽을 떼어낸 판본 — 도면이 스스로 밝힌 시트라 "
                         "func_pages 라우팅에서도 가중치 3.0 을 받는 근거다")
    ap.add_argument("--sig-union", action="store_true", default=False,
                    help="어휘 선택과 LLM 선택을 **합집합**으로 쓴다(각 sig_pick 개). "
                         "6칸 경쟁에서 정답 신호가 밀려나는 것을 막는다")
    ap.add_argument("--must-subsys", action="store_true", default=False,
                    help="강제 언급 목록에서 질문 계통 밖의 전역 신호를 뺀다. "
                         "규칙1(상위 N 반드시 언급)과 규칙6(계통 밖 신호 금지)의 충돌 해소")
    ap.add_argument("--must-top", type=int, default=12,
                    help="답변에 반드시 언급시킬 상위 근거 수. 상위 5 강제는 100%% 지켜지지만 "
                         "6~16위의 gold가 인용되지 않아 생성 단계에서 6개를 잃고 있었다. "
                         "12로 올리면 생성 손실 0 = 근거풀 상한(67.6%%) 달성")
    ap.add_argument("--max-tok", type=int, default=1200, help="답변 생성 토큰 상한")
    ap.add_argument("--parts-desc", action="store_true", default=False,
                    help="골라 준 부품을 태그만이 아니라 **설명과 함께** 생성 프롬프트에 넣는다. "
                         "태그만 주면 생성기가 그 부품이 무엇인지 몰라 점검 순서에 못 넣는다")
    ap.add_argument("--continuation-show", action="store_true", default=False,
                    help="연속 시트를 기기 제시(--index-page-devices)에도 포함(기본은 판독만)")
    ap.add_argument("--continuation", action="store_true", default=False,
                    help="상위 3쪽의 앞뒤 쪽이 제목이 같으면(연속 시트) 판독·제시 대상에 추가")
    ap.add_argument("--validate-addrs", action="store_true", default=False,
                    help="답변의 주소 토큰 중 인덱스에 없는 것을 되돌려 교정/삭제시키는 검증 패스")
    ap.add_argument("--drop-unindexed-dwg", action="store_true", default=False,
                    help="(snap 뒤) 인덱스에 없는 8자 이상 판독 신호명을 근거에서 제거")
    ap.add_argument("--io-page-route", type=float, default=0.0,
                    help="고른 신호가 인쇄된 I/O 쪽 자체에 주는 라우팅 가중치(0=끔, 상호참조는 3.0)")
    ap.add_argument("--layout-route", action="store_true", default=False,
                    help="위치를 묻는 질문이면 제목이 배치/레이아웃인 쪽을 판독 대상에 추가")
    ap.add_argument("--feasible", action="store_true", default=False,
                    help="생성 규칙 9: 고장 상태에서 실행 가능한 점검만(화면이 죽으면 물리 점검)")
    ap.add_argument("--addr-circuit", type=int, default=0,
                    help="상위 N개 신호마다 회로도 쪽별 기록에서 그 주소가 실제로 연결된 기기 줄을 근거에 추가(P334)")
    ap.add_argument("--driver-signals", type=int, default=0,
                    help="골라진 부품 시트를 상호참조로 가리키는 I/O 신호 N개를 근거에 추가(P331)")
    ap.add_argument("--coil-feed", action="store_true", default=False,
                    help="근거에 [코일 급전·직렬 접점] 블록: 후보 기기의 회로도 기록 중 코일·13-14·A1 줄(P328)")
    ap.add_argument("--feed-source", type=int, default=0, help="P352: 상위 쪽 전위선이 가리키는 시트의 전위·보호기기 행 N줄")
    ap.add_argument("--button-trigger-strict", action="store_true", help="P353: 버튼 블록 트리거에서 '전원'·'켜' 단독 제외")
    ap.add_argument("--polarity-rule", action="store_true", help="입력 극성·운전 상태는 출처에 명시된 범위만 설명")
    ap.add_argument("--feed-source-rule", action="store_true", help="P359: [급전원] 블록 보호기기를 전원 공급 단계에 — 규칙 13")
    ap.add_argument("--polarity-rule2", action="store_true", help="출처에 근거한 극성 설명 (--polarity-rule 호환)")
    ap.add_argument("--feed-cover", action="store_true", help="P363: [급전원] 전위 행의 'from <기기>' 를 부품 보완 강제 대상으로")
    ap.add_argument("--button-first", action="store_true", help="P349: 버튼 블록에서 실물 버튼 태그를 앞으로")
    ap.add_argument("--meta-cut", action="store_true", help="P349: 재작성 지시에 답하는 메타 문장 줄 삭제")
    ap.add_argument("--button-block", type=int, default=0,
                    help="리셋·전원·비상정지·기동 질문이면 문서 전체의 운전자 버튼 기록 N줄을 근거에(P348)")
    ap.add_argument("--operator-buttons", action="store_true", default=False,
                    help="코일 블록에 푸시버튼·자기유지 기록 포함 + 규칙: 리셋·전원 투입에 누를 버튼을 쓴다(P346)")
    ap.add_argument("--validate-tags", action="store_true", default=False,
                    help="답의 DIN 형식 기기 태그(-A7-02K11 류) 중 인덱스에 없는 것을 교정·삭제(P342)")
    ap.add_argument("--verify-links", action="store_true", default=False,
                    help="정리 패스가 연결 주장(구동·직렬·급전)을 회로도 기록과 대조해 근거 없는 것을 지움(P336)")
    ap.add_argument("--prune", action="store_true", default=False,
                    help="최종 정리 패스: 인덱스 부품 설명과 대조해 역할 오기를 고치고, 고장 경로 밖 "
                         "항목은 본문에서 [참고] 절로 옮긴다(삭제 없음)")
    ap.add_argument("--snap-dwg", action="store_true", default=False,
                    help="판독 신호명이 인덱스에 없고 인덱스 이름과 편집거리 1 이면 인덱스 표기로(8자 이상)")
    ap.add_argument("--prioritize", action="store_true", default=False,
                    help="생성 규칙 8: 본문은 원인 체인만, 나머지는 [참고] 절로(군더더기 분리)")
    ap.add_argument("--full-names", action="store_true", default=False,
                    help="생성 규칙 7: 신호명 전체 표기(축약·슬래시 병합 금지) + 부품 모델·정격 병기")
    ap.add_argument("--parts-tournament", action="store_true", default=False,
                    help="카탈로그를 --cat-max-chars 조각으로 나눠 조각별 선택 후 결선(절단 없음)")
    ap.add_argument("--page-parts", type=int, default=0,
                    help="라우팅된 회로 쪽에 그려진 부품 중 N개를 2차로 더 고른다(큰 카탈로그용)")
    ap.add_argument("--page-parts-pages", type=int, default=3,
                    help="--page-parts 후보를 뽑을 상위 회로 쪽 수")
    ap.add_argument("--index-page-devices", type=int, default=0,
                    help="라우팅 상위 K 쪽의 인덱스 기기 전부를 설명과 함께 근거로 제시")
    ap.add_argument("--index-page-devices-max", type=int, default=40,
                    help="쪽당 제시할 최대 기기 수")
    ap.add_argument("--coverage-rounds", type=int, default=1, help="보완 패스 반복 횟수")
    ap.add_argument("--coverage-max", type=int, default=0, help="보완 패스 1회에 돌려줄 최대 부품 수(0=제한 없음)")
    ap.add_argument("--cov-dev-rank", action="store_true", default=False,
                    help="--coverage-devices 후보를 질문·선택 설명과의 관련도 순으로(0점 제외)")
    ap.add_argument("--coverage-devices", type=int, default=0,
                    help="보완 패스 대상에 회로도 판독 기기(용도 읽힌 것) 최대 N개 추가")
    ap.add_argument("--coverage-pass", action="store_true", default=False,
                    help="답변 후 빠진 골라 준 부품을 찾아 **두 번째 생성**으로 보완한다(생성 2회). "
                         "토큰 상한을 풀어도 K4(골라 줬는데 안 씀)가 줄지 않아서 넣었다")
    ap.add_argument("--parts-top", type=int, default=6,
                    help="pick_parts 가 고를 부품 수. 실측(v6 실패 분해): 카탈로그에 있었는데 "
                         "6칸에 못 든 부품(K3)이 5건. 성능 우선이면 늘린다 — 기본은 기존값 6")
    ap.add_argument("--devices", action="store_true",
                    help="회로 도면에서 부품 태그 별도 패스로 수집(-KM41 등)")
    ap.add_argument("--explain", default=str(CACHE / "explain_dict_fixed.json"),
                    help="어드레스→신호명·부품태그·부품설명·시트 설명 사전. 기본값은 "
                         "**접두어 패치본** — 원래 사전은 페이지 규칙으로 X/Y를 강제 교정해 "
                         "gold 출력을 손상시켰다(`Y0.2 COOLANT PUMP MOTOR ON` → `X0.2`). "
                         "`exp_agentic/patch_explain_prefix.py`로 어드레스만 되돌린다(53개). "
                         "라벨일치 71→79%%, 방향오류 2→0건, 나머지 지표 불변")
    # ── 다문서 확장. 기본값은 전부 오늘 동작 그대로 ──────────────────
    ap.add_argument("--pdf", default="", help="비우면 오늘처럼 PUMA280을 glob 한다")
    ap.add_argument("--qa", default=str(GOLD), help="질문 JSON. gold 없이도 돌아간다")
    ap.add_argument("--cache", default=str(CACHE),
                    help="chunks.parquet / page_index.json 을 찾을 곳. 둘 다 없으면 건너뛴다")
    ap.add_argument("--docid", default="", help="산출 JSON에 기록할 문서 식별자")
    ap.add_argument("--doc-key", default="", help="렌더 캐시 출처 검증용 PDF 지문")
    ap.add_argument("--ref-re", default=r"\(?(\d{5})\s*/\s*(\d)\)?",
                    help="시트참조 정규식. 벤더마다 다르다 — 안 맞으면 가중치 3.0 트랙이 통째로 죽고 "
                         "라벨에 참조 문자열이 붙은 채 남아 선택 목록을 중복시킨다")
    ap.add_argument("--addr-re", default="",
                    help="회로 시트 판독에 쓸 어드레스 정규식. **비우면 PUMA 문법**이라 "
                         "MAZAK·DECKEL 도면에서 모델이 없는 점표기를 지어낸다 "
                         "(실측: INTEGREX에서 커넥터 X232를 보고 `X232.2`를 만들어 냈다)")
    ap.add_argument("--addr-grammar", default="",
                    help="판독 프롬프트에 넣을 어드레스 문법 설명. 비우면 PUMA 기본")
    ap.add_argument("--addr-norm", default=r"([XYRGFKT])0*(\d+)\.(\d)")
    ap.add_argument("--addr-norm-sub", default=r"\1\2.\3")
    ap.add_argument("--a2p-from-rows", action="store_true", default=False,
                    help="행 단위 인덱스도 addr→page 에 접는다. page_index.json 이 없는 "
                         "신규 문서에서 역라우팅을 되살린다. **기본 꺼짐**")
    ap.add_argument("--vendor-label", default="", help="장치 판독 프롬프트의 벤더 표기")
    ap.add_argument("--device-prefix", default="", help="장치 태그 접두 설명")
    ap.add_argument("--device-examples", default="", help="장치 태그 예시. 주면 벤더 프롬프트 사용")
    ap.add_argument("--dev-re", default="", help="장치 태그 정규식. 비우면 PUMA 기본 "
                    "(`-[A-Z]{1,3}\\d{1,3}[A-Z]?`) — DMG `-B2-31Q61`은 여기서 버려진다")
    ap.add_argument("--demote-generic", action="store_true",
                    help="질문과 무관하게 매번 상위에 오는 **기계 전역 상태 신호**를 강등한다"
                         "(질문 낱말과 겹치면 그대로 둔다). 심사에서 지적된 '상투적 서두/꼬리'의 원인")
    ap.add_argument("--generic-factor", type=float, default=0.35)
    ap.add_argument("--chain", action="store_true",
                    help="답을 **지령→릴레이→접촉기→보호기→모터→케이블** 순의 부하 경로로 쓰게 한다. "
                         "gold 는 예외 없이 이 경로를 따라가는데 우리 답은 릴레이에서 멈춘다(P159)")
    ap.add_argument("--show-direction", action="store_true", default=False,
                    help="근거줄에 [입력]/[출력]을 붙이고 생성기에 서술 규칙을 준다. "
                         "기본 꺼짐 — PUMA 기준선 불변")
    ap.add_argument("--query-expand", action="store_true", default=False,
                    help="신호·부품 선택 **전에** 질문을 도면 영어 어휘로 확장하고 그 어휘로 "
                         "카탈로그를 좁힌다. 기본 꺼짐 — PUMA 기준선 불변")
    ap.add_argument("--shortlist", type=int, default=10,
                    help="확장어 토큰 매칭으로 **근거풀에 추가**할 이름 수. 실측 상한: 10→22/34 · 20→23 · 40→25 (현행 18)")
    ap.add_argument("--sig-select", default="llm", choices=["llm", "lexical", "hybrid"],
                    help="신호 선택 방식. lexical=질문어 매칭 점수(결정적) · "
                         "hybrid=어휘 상위 절반 + LLM 나머지. 기본 llm — 기준선 불변")
    ap.add_argument("--catalog-descriptive", action="store_true", default=False,
                    help="신호 선택 카탈로그에서 니모닉·장치태그만 있는 라벨을 뺀다"
                         "(`TROT.M (SB100)`). 기본 꺼짐 — PUMA 기준선 불변")
    ap.add_argument("--cat-max-chars", type=int, default=12000,
                    help="부품·시트 선택 카탈로그 상한. PUMA는 4134/4170자라 무동작이지만, "
                         "310쪽짜리 INTEGREX는 이게 없으면 HTTP 400으로 1번 문항에서 죽는다")
    ap.add_argument("--resume", action="store_true", help="--out 에 있는 id 는 건너뛴다")
    args = ap.parse_args()

    global ADDR_NORM, _NORM_SUB
    ADDR_NORM = re.compile(args.addr_norm)
    _NORM_SUB = args.addr_norm_sub
    _CACHE = Path(args.cache)
    import puma_read as _pr
    _READ_RE = re.compile(args.addr_re) if args.addr_re else None
    _READ_SYS = (_pr.READ_SYS_TMPL.format(grammar=args.addr_grammar)
                 if args.addr_grammar else None)
    pdf = args.pdf or glob.glob(str(ROOT / "data/electrical-drawing/*PUMA280*.pdf"))[0]
    titles = json.loads(Path(args.titles).read_text(encoding="utf-8"))["pages"]
    parts = json.loads(Path(args.parts).read_text(encoding="utf-8"))["parts"]
    # chunks_df 는 LookupIndex 의 ptype 계산에만 쓰이고, ptype 은 score_pages 에서만 읽힌다.
    # build_addr2page 는 page_addrs 만 쓰므로 이 경로에서는 **죽은 값**이다 → 없으면 None.
    _cp = _CACHE / "chunks.parquet"
    chunks_df = None
    if _cp.exists():
        import pandas as pd
        chunks_df = pd.read_parquet(_cp)
    a2l, l2a, a2c = load_io_dict(args.io)
    # --- 행 단위 인덱스(라벨 정확도 61%) + **어드레스별 시트 참조** ---
    # I/O MAP은 각 셀에 시트 참조를 인쇄한다(`X33.6 … (07011/5)`). 190개 중 183개가
    # 표제란 인덱스(도면번호 중간 5자리)와 매핑돼 **어드레스→회로시트 직결**이 된다.
    a2sheet = {}
    _rows_path = Path(args.io_rows)
    if _rows_path.exists():
        _ti = json.loads(Path(args.titles).read_text(encoding="utf-8"))["pages"]
        _code2p = defaultdict(set)
        for _o in _ti:
            for _c in _o.get("sheet_codes", []):
                _code2p[_c].add(str(_o["page"]))
        _ref = re.compile(args.ref_re)
        for e in json.loads(_rows_path.read_text(encoding="utf-8"))["entries"]:
            a = norm(e["address"])
            labs = [x for x in (e.get("labels") or []) if x and not _ref.fullmatch(str(x).strip())]
            # **라벨 정규화(v13)** — 병합 인덱스는 같은 이름을 시트참조 유무 두 벌로 갖는다
            # (`DOOR CLOSE & LOCKING STATE (08053/3)` + `DOOR CLOSE & LOCKING STATE`).
            # 이 중복이 후보 1·2위를 차지하면 점수 차가 0이 되어 `is_uncertain`이 항상 참이 되고,
            # 근거의 93%가 "(라벨 불확실)"로 표시돼 변별력을 잃는다(v12 실측 158/169).
            # 시트참조를 떼고 대소문자·공백 무시로 중복을 제거한다.
            if args.norm_labels:
                seen_lab, ded = set(), []
                for x in labs:
                    core = re.sub(r"\s*\(?\d{5}\s*/\s*\d\)?\s*", " ", str(x)).strip()
                    core = re.sub(r"\s{2,}", " ", core)
                    k = core.upper()
                    if core and k not in seen_lab:
                        seen_lab.add(k); ded.append(core)
                labs = ded
            if labs:
                cur = a2l.get(a, [])
                for l in reversed(labs):
                    if l not in cur:
                        cur.insert(0, l)          # 행단위 라벨을 앞에 (더 정확)
                # 기존 후보에도 같은 이름의 변형이 있으면 정리
                if args.norm_labels:
                    seen2, keep = set(), []
                    for l in cur:
                        k = re.sub(r"\s*\(?\d{5}\s*/\s*\d\)?\s*", " ", str(l)).strip().upper()
                        if k and k not in seen2:
                            seen2.add(k); keep.append(l)
                    cur = keep
                a2l[a] = cur[:3]
                for l in labs:
                    l2a[l.upper()].add((a, str(e["page"])))
                a2c[a] = "high"
            if not args.ref_index:
                for l in (e.get("labels") or []):
                    m = _ref.search(str(l))
                    if m:
                        pgs = sorted(_code2p.get(m.group(1), ()), key=int)
                        if pgs:
                            a2sheet[a] = pgs
                        break
        # 시트참조를 별도 인덱스에서 가져오는 경우(합의 필터본)
        if args.ref_index and Path(args.ref_index).exists():
            a2sheet = {}
            for e in json.loads(Path(args.ref_index).read_text(encoding="utf-8"))["entries"]:
                a = norm(e["address"])
                for l in (e.get("labels") or []):
                    m = _ref.search(str(l))
                    if m:
                        pgs = sorted(_code2p.get(m.group(1), ()), key=int)
                        if pgs:
                            a2sheet[a] = pgs
            log.info(f"시트참조를 {Path(args.ref_index).name}에서 로드: {len(a2sheet)} addr")
        log.info(f"행단위: 라벨 {len(a2l)} addr, 시트참조 {len(a2sheet)} addr")
    a2p = build_addr2page(args.io, args.signals, _CACHE / "page_index.json", chunks_df,
                          rows_path=(args.io_rows if args.a2p_from_rows else None))
    EX = {}
    if Path(args.explain).exists():
        for e in json.loads(Path(args.explain).read_text(encoding="utf-8"))["entries"]:
            EX[norm(e["address"])] = e
        log.info(f"설명 사전 {len(EX)} addr (부품태그 보유 "
                 f"{sum(1 for v in EX.values() if v.get('tag'))})")
    # 장치 태그 판독의 벤더 설정. 안 넘기면 PUMA 예시·PUMA 정규식으로 남의 도면을 읽는다.
    _dev_sys = (DEVICE_SYS_TMPL.format(vendor=args.vendor_label, prefix=args.device_prefix,
                                       examples=args.device_examples)
                if args.device_examples else None)
    _dev_re = re.compile(args.dev_re) if args.dev_re else None
    tmp = Path(args.tmp) if args.tmp else Path(os.environ.get("TMPDIR", "/tmp")) / "puma_v5"

    code2page = defaultdict(set)
    for o in titles:
        for c in o.get("sheet_codes", []):
            code2page[c].add(str(o["page"]))
    sym = {p["symbol"]: p for p in parts}
    # 쪽 → 그 쪽에 그려진 부품(시트 코드를 쪽으로 푼다). `--index-page-devices` 용.
    page2parts = defaultdict(list)
    # 인덱스가 쪽별 기기 표를 주면 그것을 쓴다(그 쪽에서 읽은 설명 — P269). 없으면 통합 부품에서 유도.
    _pdev_json = json.loads(Path(args.parts).read_text(encoding="utf-8")).get("page_devices") if args.parts else None
    for _pg, _its in (_pdev_json or {}).items():
        page2parts[str(_pg)] = list(_its)
    for p in ([] if _pdev_json else parts):
        if not p.get("description"):
            continue
        if str(p.get("sheet_prov", "")).startswith("parts_list"):
            continue                       # 부품표 자리채움은 그 부품이 그려진 쪽이 아니다
        _ps = set()
        for c in (p.get("sheets") or []):
            _ps.update(str(x) for x in code2page.get(c, ()))
        for _pg in _ps:
            page2parts[_pg].append(p)
    page_title = {str(o["page"]): o.get("title", "") for o in titles}
    # 기호 → 쪽별 기록(그 쪽에서의 역할·접점). `--prune` 이 역할 대조에 쓴다(P316): 통합 카탈로그
    # 설명엔 "GV2ME08; aux GVAE11" 뿐이지만 p22 기록엔 "aux 13-14 in coolant pump contactor circuit".
    sym_pnotes = defaultdict(list)
    for _pg, _its in page2parts.items():
        for _pt in _its:
            sym_pnotes[str(_pt.get("symbol", "")).upper().strip("-")].append((str(_pg), _pt.get("description", "")))
    # 주소·신호명 → 회로도 쪽별 기록(`--addr-circuit`, P334). I/O 맵의 태그(PUMA Y2.4 = KA21P)와
    # 회로 시트의 실제 기기(KA26)가 다른 경우가 있어, 회로 시트 쪽 기록을 따로 보여 준다.
    pdev_all = [(str(_pg), str(_pt.get("symbol", "")), str(_pt.get("description", "")))
                for _pg, _its in page2parts.items() for _pt in _its]
    coil_rev = defaultdict(list)
    _crx0 = re.compile(r"coil|13-14|13/14|\bA1\b|PWR AUX|power supply|fed (from|via)|supply .* for", re.I)
    for _s, _lst in sym_pnotes.items():
        for _pg, _d in _lst:
            if not _crx0.search(str(_d)):
                continue
            for _m in re.findall(r"-?[A-Z]\d-\d{2}[A-Z]\d{2}|-[A-Z]{1,3}\d{1,4}[A-Z]?", str(_d)):
                _k = _m.upper().strip("-")
                if _k and _k != _s:
                    coil_rev[_k].append((_s, _pg, _d))

    llm = LLM(os.environ.get("LLM_NAME", "gemma4"), backend="vllm_api",
              api_base=os.environ.get("VLLM_API_BASE", "http://127.0.0.1:8001/v1"),
              api_model=os.environ.get("VLLM_API_MODEL", "gemma4"))
    qa = json.loads(Path(args.qa).read_text(encoding="utf-8"))["qa_pairs"]
    if args.n:
        qa = qa[:args.n]
    prior = {}
    if args.resume and Path(args.out).exists():
        try:
            _prev = json.loads(Path(args.out).read_text(encoding="utf-8"))
            # ⚠ **인덱스가 바뀌었으면 재개하지 않는다.** 인덱스를 다시 만들고 파이프라인을
            #   그대로 돌리면 `--resume` 이 옛 답변을 전부 보존해, 지표가 **한 자리도 안 움직인
            #   채** 개선이 없다고 결론 내리게 된다(실측: SL2500 컬럼 판독으로 이름 40개가
            #   전부 바뀌었는데 페이지 recall·키워드 커버리지가 소수점까지 동일했다).
            _ps = _prev.get("summary", {})
            _sig = {k: _index_sig(getattr(args, k, "")) for k in ("explain", "io_rows", "io")}
            _old = _ps.get("index_sig") or {}
            if _old and _old != _sig:
                log.warning(f"재개 취소 — 인덱스가 바뀌었다 {[(k, _old.get(k), v) for k, v in _sig.items() if _old.get(k) != v]}")
            else:
                for r in _prev.get("rows", []):
                    prior[r.get("id")] = r
                log.info(f"재개: {len(prior)}문항 이미 답변됨")
        except Exception as e:
            log.warning(f"재개 실패(무시): {e}")
    log.info(f"v5: I/O 사전 {len(a2l)} addr / {len(l2a)} names, addr→page {len(a2p)}, n={len(qa)}")

    rows, recs = [], []
    _qcache = {}
    _idf = build_idf(list(l2a.keys()))
    # 기계 전역 신호는 **문서당 한 번** 정하고 캐시한다(문항마다 부르면 10배 낭비).
    GENERIC = (generic_signals(llm, list(a2l.keys()),
                               _CACHE / "generic_signals.json",
                               labels=a2l)
               if args.demote_generic else set())
    t0 = time.time()
    for i, it in enumerate(qa):
        if it.get("id") in prior:
            r = prior[it["id"]]
            rows.append(r)
            if r.get("addr", {}).get("recall") is not None:
                recs.append(r["addr"]["recall"])
            log.info(f"[{i+1}/{len(qa)}] {it.get('id')}: 재개 — 건너뜀")
            continue
        q = it["question"]; gaddr = it.get("key_addresses", [])
        _parts_in = parts
        if args.query_expand:
            _t = expand_query(llm, q, _qcache)
            _cand = [p for p in parts
                     if any(t in str(p.get("description", "")).upper() for t in _t if len(t) >= 3)]
            if _cand:
                _parts_in = _cand[:args.shortlist]
        # `--cat-relevance` 는 한국어 질문에서 ASCII 토큰이 안 나와 그대로는 무효다
        # (실측 9/10 문항). 계통 정규식을 함께 넘겨 한국어 질문 ↔ 영문 카탈로그를 잇는다.
        if args.parts_tournament:
            # **토너먼트 선택** — 큰 카탈로그(SL2500 v4: 1056기호 89k자)는 상한에서 자르면 K2,
            # 상한을 풀면 수백 개 중 고르다 K3 로 잃는다(P246). 상한 크기 조각마다 고르고
            # 조각 승자끼리 결선을 치러 **절단 없이** 전부를 한 번씩 보게 한다. 조각·결선 모두
            # 출력을 해당 후보 기호로 거른다(`pick_parts` 는 목록 밖 태그를 낸다, P250).
            _elig = [pt for pt in _parts_in if pt.get("description") and pt.get("sheets")]
            _chunks, _cur, _n = [], [], 0
            for pt in _elig:
                _l = len(pt["symbol"]) + len(pt["description"]) + 3
                if _cur and _n + _l > args.cat_max_chars:
                    _chunks.append(_cur); _cur, _n = [], 0
                _cur.append(pt); _n += _l
            if _cur:
                _chunks.append(_cur)
            _bysym = {str(pt["symbol"]).upper(): pt for pt in _elig}
            _win = []
            for _ch in _chunks:
                _ok = {str(pt["symbol"]).upper() for pt in _ch}
                for x in pick_parts(llm, q, _ch, top=args.parts_top, max_chars=0):
                    if x.upper() in _ok and x.upper() not in _win:
                        _win.append(x.upper())
            _final = [_bysym[x] for x in _win]
            picked_parts = [x for x in pick_parts(llm, q, _final, top=args.parts_top,
                                                  max_chars=args.cat_max_chars,
                                                  relevance=args.cat_relevance,
                                                  qrx=question_subsys(q) if args.cat_relevance else ())
                            if x.upper() in _bysym] if len(_chunks) > 1 else \
                           [x for x in _win][:args.parts_top]
            picked_parts = [_bysym[x.upper()]["symbol"] for x in picked_parts]
            log.info(f"    토너먼트: {len(_elig)}기호 {len(_chunks)}조각 → 결선 {len(_win)} → {len(picked_parts)}")
        else:
            picked_parts = pick_parts(llm, q, _parts_in, top=args.parts_top,
                                      max_chars=args.cat_max_chars,
                                      relevance=args.cat_relevance,
                                      qrx=question_subsys(q) if args.cat_relevance else ())
        # 선택 프롬프트에는 **서술형 이름만** 넣는다 — 코드((SX31))·셀번호·시트참조는 선택에
        # 무용한데 목록을 부풀려 컨텍스트를 넘긴다(병합 인덱스에서 991개 ≈ 5.9k 토큰 → HTTP 400).
        _names = []
        for n in l2a:
            n2 = re.sub(r"\s*\(\d{5}\s*/\s*\d\)\s*", "", n).strip()   # 시트참조 제거
            # **니모닉/기능문 분리(P134)** — 현재 잡음 판정은 *길이*로 한다. 그래서 니모닉
            # 하나(`TROT.M`, 6자)는 걸러지는데 니모닉+태그(`TROT.M (SB100)`, 14자)는
            # **통과한다**. 실측: 이 두 개가 터렛 문항의 신호 6칸 중 2칸을 먹고 gold
            # `X4.6`은 판독조차 되지 않았다(P133). 니모닉과 장치태그를 **떼어 낸 뒤**
            # 기능문이 남는지로 판정하면 길이와 무관하게 걸러진다. 니모닉은 `a2l`에
            # 그대로 남으므로 근거 표시·판독에는 손실이 없다 — 카탈로그에서만 뺀다.
            if args.catalog_descriptive:
                n2 = re.sub(r"\(\s*-?[A-Z]{1,4}\d{1,4}[A-Z0-9]{0,2}\s*\)", " ", n2)
                n2 = re.sub(r"(?<![A-Z0-9])\$?[A-Z0-9]{1,7}\.[A-Z](?![A-Z0-9])", " ", n2)
                n2 = re.sub(r"^\s*[A-Z]?\d{1,3}\s+", " ", n2)          # 앞 셀번호
                n2 = re.sub(r"\s{2,}", " ", n2).strip()
            if len(n2) >= 6 and re.search(r"[A-Z]{3,}", n2) and not n2.startswith("$") \
                    and not re.fullmatch(r"[\(\)A-Z0-9./ -]{0,12}", n2):
                _names.append(n)
        # **선택 목록만 중복 제거(v22)** — `CYCLE START`와 `CYCLE START (07011/5)`가 둘 다
        # 후보로 올라가 상위 6칸 중 한 칸을 낭비한다(실측 68칸 중 8칸 = 12%).
        # 자동문 문항은 그 한 칸 때문에 `AUTO DOOR SAFETY EDGE SENSOR ON`(gold X12.4)이
        # 6위 밖으로 밀렸다. ⚠️ v13a처럼 `a2l`·`lab_cover`를 정규화하면 반복라벨 감점
        # 대상이 늘어 순위가 망가진다(recall 50.0→44.1%). 여기서는 **LLM에게 보여줄
        # 목록만** 줄이고 순위 계산은 원본 그대로 둔다.
        if args.dedup_names:
            _seen, _ded = {}, []
            for n in _names:
                c = re.sub(r"\s*\(?\d{5}\s*/\s*\d\)?\s*", " ", n).strip().upper()
                c = re.sub(r"\s{2,}", " ", c)
                if c not in _seen or len(n) < len(_seen[c]):
                    _seen[c] = n
            _names = list(_seen.values())
        if len(_names) > 600:
            _names = sorted(_names, key=lambda x: -len(x.split()))[:600]
        _cat = _names or list(l2a.keys())
        _terms, _extra = [], []
        if args.query_expand:
            _terms = expand_query(llm, q, _qcache)
            # ⚠ 카탈로그를 **대체하지 않는다**. 좁힌 목록만 주면 현행이 찾던 이름까지
            #   버려서 gold 도달이 오히려 떨어진다(실측 cycle-start 4→1). LLM의 6칸은
            #   그대로 두고, 토큰 매칭으로 찾은 이름을 **근거풀에 추가**한다 —
            #   6칸 경쟁을 건드리지 않고 '닿을 수 있는데 안 뽑히던' 11개를 노린다.
            _extra = shortlist_by_terms(_terms, _cat, args.shortlist, _idf)
            log.info(f"    질의 확장 {len(_terms)}어 {_terms[:5]} → 보강 후보 {len(_extra)}")
        if args.sig_select == "llm" and not args.sig_union:
            picked_sigs = pick_signals(llm, q, _cat, top=args.sig_pick)
        else:
            _lex = lexical_signals(q, _cat, l2a, top=args.sig_pick)
            if args.sig_select == "llm":            # --sig-union 으로 들어온 경우
                args.sig_select = "union_llm"
            if args.sig_select == "lexical":
                # 축이 하나도 안 걸리면 어휘식은 아무것도 못 고른다 → LLM으로 되돌린다.
                picked_sigs = _lex or pick_signals(llm, q, _cat, top=args.sig_pick)
            elif args.sig_union:
                # **합집합** — 6칸을 나눠 갖지 않는다. IO 트랙은 여기서 고른 신호로만
                # 어드레스를 만들므로, 한 칸이라도 밀리면 그 어드레스는 근거에 못 든다
                # (실측: SL2500 터릿에서 X1.7 클램프확인이 클램프램프·MACHINE READY에
                #  밀려 최종 생성기에 도달조차 못 했다). 둘 다 보여 주고 순위는
                #  뒤의 rank/rerank 가 정하게 한다.
                _llm = pick_signals(llm, q, _cat, top=args.sig_pick)
                picked_sigs = _lex + [x for x in _llm if x not in _lex]
            else:                                   # hybrid — 어휘 상위 절반 + LLM 나머지
                _half = max(1, args.sig_pick // 2)
                _llm = pick_signals(llm, q, _cat, top=args.sig_pick)
                picked_sigs = _lex[:_half] + [x for x in _llm if x not in _lex[:_half]]
                picked_sigs = picked_sigs[:args.sig_pick]
            log.info(f"    어휘 선택({args.sig_select}) {len(_lex)}개: {_lex[:4]}")
        # **질문어 직접 매칭(v14)** — 질문에 인쇄된 이름이 그대로 들어 있으면 LLM 판단을 기다리지
        # 않는다. 실측: "CYCLE START 버튼 눌러도 동작 안 해요"에서 LLM은 인터록 신호만 고르고
        # 사전에 있는 CYCLE START(=gold X33.6)를 빠뜨렸다.
        if args.q_match:
            _qu = q.upper()
            _forced = []
            for _n in l2a:
                _core = re.sub(r"\s*\(?\d{5}\s*/\s*\d\)?\s*", " ", _n).strip().upper()
                if len(_core) >= 5 and _core in _qu and len(l2a[_n]) <= 4:
                    _forced.append(_n)
            if _forced:
                picked_sigs = _forced + [s for s in picked_sigs if s not in _forced]
                log.info(f"    질문어 직접 매칭: {_forced}")
        # **fan-out 수정(격리 검증)** — 선택 순서대로 어드레스를 담고 [:N]으로 자르면 앞선
        # 신호가 예산을 독식한다. 특히 행 정렬이 밀린 라벨은 fan-out이 크다
        # (`FEED HOLD` → X33.0~X33.7 8개). 라운드로빈 + fan-out 상한으로 예산 낭비 제거.
        signal_names = list(picked_sigs) + [x for x in _extra if x not in picked_sigs]
        by_sig = [(nm, sorted(l2a.get(nm.upper(), ()))) for nm in signal_names
                  if 0 < len(l2a.get(nm.upper(), ())) <= 4]
        route_hits = collect_signal_hits(signal_names, l2a, a2l)
        sig_hits = route_hits[:args.sig_top + (args.shortlist if _extra else 0)]
        circuit_pages = signal_circuit_pages(route_hits, a2sheet, parts, code2page, EX)

        # 트랙 1 — 기능 시트 (부품 SHEET NO 라우팅 + 표제란 제목)
        # 세 트랙의 기여를 따로 적어 둔다 — 사후에 "왜 이 페이지를 폈나"를 사람이 검증할 수
        # 있어야 한다(`scripts/build_trace_html.py`). 점수 계산 자체는 그대로다.
        score = defaultdict(float)
        tr_parts, tr_titles, tr_refs = [], [], []
        for r, s in enumerate(picked_parts):
            _pgs = []
            for c in sym.get(s, {}).get("sheets", []):
                for p in code2page.get(c, ()):
                    score[p] += 1.0 / (1 + r)
                    _pgs.append([c, p, round(1.0 / (1 + r), 3)])
            if _pgs:
                tr_parts.append({"symbol": s, "hits": _pgs})
        for r, p in enumerate(pick_sheets(llm, q, titles, top=3, max_chars=args.cat_max_chars,
                                          relevance=args.cat_relevance)):
            score[p] += 1.5 / (1 + r)
            tr_titles.append({"page": p, "title": page_title.get(p, ""),
                              "w": round(1.5 / (1 + r), 3)})
        # **어드레스 시트 참조 라우팅** — 도면이 스스로 밝힌 시트라 부품 라우팅보다 정확
        # ⚠ 단 **전역 신호일 때는 그렇지 않다.** `--demote-generic` 은 근거 **순위**만
        #   손보고 이 라우팅 가중치에는 적용되지 않는다. 실측(dmu85-sym-002, 24V 제어전원):
        #   POWERFAIL·PLC_RDY·EMERGENCY STOP·CNC_READY 의 시트가 3.0 가중으로 6쪽 예산 중
        #   **4칸**을 먹었고, 제목 트랙이 gold 3쪽을 1·2·3위로 정확히 잡았는데도 가중이
        #   절반(1.5)이라 3순위 p27(0.50)이 잘렸다. 질문이 그 계통을 묻지 않는 전역 신호는
        #   라우팅에서도 깎는다 — `demote_generic` 과 **같은 면제 기준**을 쓴다.
        _rt_qrx = question_subsys(q) if args.route_demote_generic else []
        _sig_score, tr_refs = score_signal_pages(
            route_hits, a2sheet, page_title, args.io_page_route,
            GENERIC if args.route_demote_generic else (), _rt_qrx, args.route_demote_factor)
        for _p, _w in _sig_score.items():
            score[_p] += _w
        # **결정적 타이브레이크(v25)** — score/cand_pages의 키는 set 순회로 들어와 삽입 순서가
        # 실행마다 달라진다(PYTHONHASHSEED 무작위). 동점이면 정렬이 뒤집혀 읽는 페이지가 바뀌고,
        # A/B 비교에 잡음이 섞인다(실측: 사전만 바꿨는데 rev_pages가 3문항에서 달라짐).
        _ranked_pages = sorted(score.items(), key=lambda kv: (-kv[1], int(kv[0])))[:args.func_pages]
        func_pages = [p for p, _ in _ranked_pages]
        # **연속 시트(`--continuation`, P303).** 한 회로가 같은 제목으로 여러 장에 걸친다(SL2500
        # 16→17 3-PHASE MOTOR CONNECTION, 68→69 AMP DIAGRAM, 75→76 I/O LINK INTERFACE). 상위 쪽만
        # 읽으면 뒷장의 기기를 놓친다 — 정답 쪽 손실 16 중 이런 경우가 여럿. 상위 3쪽의 앞뒤 쪽이
        # 회로 제목의 말미 장 번호를 제외하고 같으면 판독·제시 대상에 붙인다.
        _cont = []
        if args.continuation:
            _explicit_pages = {p for pages in circuit_pages.values() for p in pages}
            for _pg in func_pages[:3]:
                # 명시된 신호·부품 연결이 있으면 같은 제목의 별도 회로로 넓히지 않는다.
                if str(_pg) in _explicit_pages:
                    continue
                try:
                    _n = int(_pg)
                except ValueError:
                    continue
                _t = page_title.get(str(_pg), "").strip().upper()
                # MAP/LIST pages are independent tables, not a continued circuit.
                if re.search(r'\b(?:MAP|LIST)\b', _t):
                    continue
                _t = re.sub(r'\s*\(\d+\)\s*$', '', _t)
                for _nb in (str(_n + 1), str(_n - 1)):
                    if _t and re.sub(r'\s*\(\d+\)\s*$', '', page_title.get(_nb, "").strip().upper()) == _t \
                            and _nb not in func_pages and _nb not in _cont:
                        _cont.append(_nb)
            if _cont:
                func_pages = func_pages + _cont
                log.info(f"    연속 시트 추가 {_cont}")
        # **위치 질문은 배치도로(`--layout-route`, P290).** "I/O 유닛이 물리적으로 어디 있나"(SL2500 Q10)에
        # 세 차례 심사 모두 "p79 EL-BOX LAYOUT·p71 미도달"을 지적했다 — 라우팅은 기능 시트만 본다.
        # 질문이 위치를 물으면 제목이 배치/레이아웃/설치판인 쪽을 판독 대상 앞에 넣는다.
        # "어디부터 봐야"(점검 순서)는 위치 질문이 아니다 — SL2500 Q1 오발동(P291).
        if args.layout_route and re.search(r"어디(?!\s*부터|서부터)|위치|배치|설치된|장착된|붙어", q):
            _lay = [str(o["page"]) for o in titles
                    if re.search(r"LAYOUT|배치|MOUNTING PLATE|CABINET OVERVIEW|SYSTEM LAYOUT",
                                 str(o.get("title", "")), re.I)]
            _lay = [x for x in _lay if x not in func_pages][:3]
            if _lay:
                # 기능 쪽을 **밀어내지 않는다** — 앞에 넣으면 `--index-page-devices` 상위 3쪽이 전부
                # 배치도가 되어 I/O Link 기능 쪽(JD1B·JD51A)을 잃었다(v27 Q10, P291). 뒤에 붙이고
                # 기기 제시는 기능 쪽 K 개 + 배치도 쪽으로 따로 센다.
                func_pages = func_pages + _lay
                log.info(f"    위치 질문 → 배치도 쪽 {_lay} 추가")
        else:
            _lay = []
        # **쪽 기준 2차 부품 선택(`--page-parts N`)** — 카탈로그가 크면(SL2500 v4: 1056기호)
        # 전체에서 6개를 고르는 방식이 무너진다: 상한 12000→30000자로 절단(K2)을 25→17 로
        # 줄였더니 미선택(K3)이 20→30 으로 늘어 점수 불변(P246). 라우팅이 고른 회로 쪽에
        # **실제로 그려진** 부품만 후보로 좁혀(수십 개) 한 번 더 고른다. 1차 선택은 라우팅에
        # 쓰이므로 그대로 두고, 2차분은 생성·보완 패스에만 더한다.
        _pp_added = []
        if args.page_parts:
            _fp = set(func_pages[:args.page_parts_pages])
            # ⚠ `sheets` 는 문서마다 **쪽 번호(SL2500)** 이거나 **시트 코드(DMU85 `A3-02`)** 다.
            #   코드를 쪽으로 풀지 않으면 DMU85 에서 후보가 0개로 조용히 꺼진다(v9f 실측 10/10).
            def _pgs(pt):
                out = set()
                for c in (pt.get("sheets") or []):
                    out.add(str(c))
                    out.update(str(x) for x in code2page.get(c, ()))
                return out
            _local = [pt for pt in parts
                      if pt.get("symbol") not in picked_parts and _fp & _pgs(pt)]
            if _local:
                _pp_added = pick_parts(llm, q, _local, top=args.page_parts,
                                       max_chars=args.cat_max_chars,
                                       relevance=args.cat_relevance,
                                       qrx=question_subsys(q) if args.cat_relevance else ())
                # `pick_parts` 는 출력이 목록에 있는지 **검사하지 않는다** — 후보 1개에서 6개가
                # 나왔다(v9f2 dmu85-sym-003). 없는 태그는 보완 패스가 답변에 강제하므로 걸러낸다.
                _ok = {str(pt.get("symbol", "")).upper() for pt in _local}
                _pp_added = [x for x in _pp_added if x.upper() in _ok]
                picked_parts = list(picked_parts) + [x for x in _pp_added if x not in picked_parts]
            log.info(f"    쪽 기준 부품: 후보 {len(_local)} → 추가 {len(_pp_added)}")
        # 라우팅이 강하게 지목한 시트에서 읽힌 어드레스는, 라벨을 못 읽었어도 강한 근거다.
        # (척 정답 Y0.6·Y0.7이 p75 MAIN CHUCK CONTROL에서 읽혔는데 9위까지 밀린 사례)
        _mx = max([v for _, v in _ranked_pages], default=1.0) or 1.0
        page_prior = {p: args.page_prior * (v / _mx) for p, v in _ranked_pages}

        # 트랙 2 — I/O MAP 이름사전(후보 라벨) → 어드레스


        # 트랙 3 — 역라우팅: 위 어드레스가 실린 시트를 추가 판독
        rev_pages, cand_pages = reverse_signal_pages(route_hits, a2p, circuit_pages, func_pages,
                                                     args.rev_pages, fallback=args.rev_fallback)

        report_progress("질문과 관련된 부품·신호·도면을 찾는 중",
                        f"선택한 도면: {', '.join('p' + str(p) for p in func_pages) or '없음'}\n"
                        f"연결 참조로 추가한 도면: {', '.join('p' + str(p) for p in rev_pages) or '없음'}\n"
                        f"검색한 부품 후보: {', '.join(picked_parts) or '없음'}\n검색 후보이며 최종 답변의 근거는 이후 검토합니다.")
        found = []
        for p in func_pages:
            report_progress(f"관련 도면 {p}쪽의 회로와 신호를 판독하는 중")
            for e in read_crops(llm, render_page(pdf, p, Path(args.render_dir), args.scale, doc_key=args.doc_key or None),
                                tmp, p, grid=(2, 2), addr_re=_READ_RE, sys_prompt=_READ_SYS):
                e["src"] = "DWG"; e["page_prior"] = page_prior.get(p, 0.0); found.append(e)
            report_progress(f"관련 도면 {p}쪽의 회로와 신호를 판독하는 중",
                            "이미지 판독에서 수집한 신호 후보: " + (', '.join(dict.fromkeys(e['address'] for e in found if str(e['page']) == str(p))) or '없음')
                            + "\n자동 판독 결과이며 아직 근거 검토 전입니다.")
        for p in rev_pages:            # 역라우팅으로 간 시트 = 사전 어드레스가 실린 곳
            report_progress(f"연결된 도면 {p}쪽의 회로와 신호를 판독하는 중")
            for e in read_crops(llm, render_page(pdf, p, Path(args.render_dir), args.scale, doc_key=args.doc_key or None),
                                tmp, p, grid=(2, 2), addr_re=_READ_RE, sys_prompt=_READ_SYS):
                e["src"] = "REV"; e["page_prior"] = args.page_prior * 0.25; found.append(e)
            report_progress(f"연결된 도면 {p}쪽의 회로와 신호를 판독하는 중",
                            "이미지 판독에서 수집한 신호 후보: " + (', '.join(dict.fromkeys(e['address'] for e in found if str(e['page']) == str(p))) or '없음')
                            + "\n자동 판독 결과이며 아직 근거 검토 전입니다.")
        found = merge_by_address(found)
        # **부품 태그 패스** — gold가 인용하는 부품(-KM41·-SX31·-SP71)은 PARTS LIST에 없고
        # 회로 도면에만 그려져 있다(측정: PARTS LIST 텍스트 10/34 vs 도면 24/34).
        # 어드레스 중심 판독은 이를 놓치므로 별도 질의로 수집한다.
        devices = []
        if args.devices:
            for p in func_pages:
                report_progress(f"도면 {p}쪽의 부품과 연결 표기를 확인하는 중")
                devices += read_devices(llm, render_page(pdf, p, Path(args.render_dir), args.scale, doc_key=args.doc_key or None),
                                        tmp, p, sys_prompt=_dev_sys, dev_re=_dev_re)
                report_progress(f"도면 {p}쪽의 부품과 연결 표기를 확인하는 중",
                                "이미지 판독에서 수집한 부품 후보: " + (', '.join(dict.fromkeys(d['device'] for d in devices if str(d['page']) == str(p))) or '없음')
                                + "\n자동 판독 결과이며 실제 부품의 상태를 확인한 것은 아닙니다.")
        report_progress("판독한 신호와 부품 정보를 정리하는 중")
        # **판독 신호명을 인덱스 표기로 맞춘다(`--snap-dwg`, P278).** 실행 중 VLM 이 p106 의
        # `ISX_SIDO_CH1_LKD` 를 `IX_SIDO_CH1_LKD` 로 읽었고(S 탈락), 인덱스엔 바른 표기가 있는데도
        # 오독이 근거 상위로 올라 답에 그대로 나갔다. 인덱스에 **없는** 판독 이름이 인덱스 이름과
        # 편집거리 1 이면 인덱스 표기로 바꾼다. 8자 이상만 — `X9.0` 같은 짧은 주소는 건드리지 않는다.
        if args.snap_dwg:
            _known = {norm(k): k for k in a2l}
            for f in found:
                _a = norm(f["address"])
                if len(_a) < 8 or _a in _known:
                    continue
                _hit = [k for k in _known if abs(len(k) - len(_a)) <= 1 and _lev1(k, _a)]
                if len(_hit) == 1:
                    log.info(f"    판독 표기 교정: {f['address']} → {_known[_hit[0]]}")
                    f["address"] = _known[_hit[0]]
        # **인덱스에 없는 판독 신호명 제거(`--drop-unindexed-dwg`, P299).** 심사(P298)가 지적한 남은
        # 날조 = 단자 라벨을 입력 신호로 읽은 것(`IX_B6_07X21_17`). 편집거리 1 교정(`--snap-dwg`) 뒤에도
        # 인덱스(할당표 전체)에 없는 **긴 이름**(8자 이상)은 오독 — 근거에서 뺀다. 짧은 주소는 둔다.
        if args.drop_unindexed_dwg:
            _known = {norm(k) for k in a2l}
            _before = len(found)
            found = [f for f in found
                     if len(norm(f["address"])) < 8 or norm(f["address"]) in _known]
            if len(found) < _before:
                log.info(f"    인덱스에 없는 판독 신호 {_before - len(found)}개 제거")
        # 판독된 어드레스에 I/O 사전 라벨을 보강 (후보 통합)
        for f in found:
            for l in a2l.get(norm(f["address"]), []):
                if l not in f["labels"]:
                    f["labels"].append(l)
            f["labels"] = f["labels"][:3]

        # --- 근거 재순위 + 라벨 신뢰도 (v6) ---
        pool = ([{**e, "src": "IO"} for e in sig_hits] +
                [{**e, "src": e.get("src", "DWG"), "page_prior": e.get("page_prior", 0.0)}
                 for e in found])
        conf, _ = label_confidence(pool)
        # 병합 인덱스의 합의 신뢰도를 반영: low는 불확실로 강등, high는 신뢰
        # 이중 감점 방지: label_confidence의 반복라벨 감점(-0.8)과 합의 신뢰도를 함께 쓰면
        # 거의 모든 항목이 '불확실'이 되어 변별력을 잃는다(v6c에서 16개 중 8~16개가 불확실).
        # 합의가 high/medium이면 반복라벨 감점을 상쇄하고, low일 때만 추가 감점한다.
        for a_, lv in a2c.items():
            if a_ in conf and conf[a_]:
                adj = {"high": 0.5, "medium": 0.0, "low": -0.6}.get(lv, 0.0)
                conf[a_] = {l: round(v + adj, 2) for l, v in conf[a_].items()}
        kws = set()
        for nm in picked_sigs:
            kws |= set(re.findall(r"[A-Z]{3,}", nm.upper()))
        for s_ in picked_parts:
            kws |= set(re.findall(r"[A-Z]{3,}", sym.get(s_, {}).get("description", "").upper()))
        for t in _terms:                      # 확장어도 점수 재료 — 없으면 보강분이 바닥 점수
            kws |= set(_content_tokens(t))
        ranked = (rank_evidence_quota(pool, kws, conf, top=args.evidence_top)
                  if args.quota else
                  rank_evidence(pool, kws, conf, kind=None, top=args.evidence_top))
        if args.rerank:
            ranked = rerank_llm(llm, q, ranked, conf, page_title,
                                args.show_top or args.evidence_top,
                                adaptive=args.rerank_adaptive)
        elif args.show_top:
            ranked = ranked[:args.show_top]
        if args.demote_generic:
            # **재순위 뒤에** 적용한다. 앞에 두면 `rerank_llm` 이 순서를 다시 매겨
            # 강등이 그대로 지워진다(실측: 강등 로그가 한 줄도 안 찍혔다).
            ranked = demote_generic(ranked, GENERIC, question_subsys(q), args.generic_factor)
        ev_top = format_evidence(ranked, conf, page_title)
        # **설명 사전 결합** — 신호 목록을 물리적 점검 설명으로 바꾸기 위한 재료.
        # gold 답변은 "릴레이 -KP3P의 LED 확인 / 마그네트 -KM41이 붙는지" 식의 부품 서술인데,
        # I/O MAP 셀이 신호마다 **부품 태그**를 인쇄하고(-SP71 등) PARTS LIST가 그 부품의
        # 종류·사양을 준다. 어드레스마다 이 정보를 붙여 생성기가 물리 점검을 쓸 수 있게 한다.
        ex_lines = []
        for _s, _kw, _a, _e in ranked:
            v = EX.get(_a)
            if not v:
                continue
            bits = [f"{_a}"]
            # **방향을 근거에 명시한다.** 안 쓰면 생성기가 이름만 보고 방향을 뒤집는다 —
            # 실측: `Y1.4 CHIP CONVEYOR EMERGENCY STOP`(출력)을 "비상 정지 신호가
            # **입력**되었는지 확인"이라 지시했다(P81이 지적한 오류가 P83 이후에도 잔존).
            # 인덱스는 고쳤지만 **제시 방식**을 안 고쳤던 것이다.
            if args.show_direction:
                _d = io_direction(_a)
                if _d:
                    bits.append(f"[{_d}]")
            if v.get("name"):
                bits.append(f"신호={v['name']}")
            if v.get("tag"):
                bits.append(f"부품=-{v['tag']}" + (f"({v['part_desc']})" if v.get("part_desc") else ""))
            if v.get("sheet"):
                bits.append(f"회로=p{v['sheet']} {v.get('sheet_title','')}")
            ex_lines.append(" | ".join(bits))
        ev_explain = "\n".join(ex_lines) or "(설명 사전 항목 없음)"
        # **부품 태그 선별(v29)** — `read_devices`는 페이지의 태그를 무차별로 긁어와
        # 문항당 18~45개를 준다. 그 결과 답변이 인용한 태그의 **정밀도가 14~19%**에 그친다
        # (독립 심사가 지적한 '고정 필러 태그': -SV13·-M24·-KM31이 4/11 문항에 반복 등장).
        # 기능 텍스트(`near`)가 함께 읽힌 태그 = 회로도가 용도를 밝힌 것만 제시한다.
        _dev = [d for d in devices if d.get("near")] if args.dev_named else devices
        if args.dev_named and not _dev:
            _dev = devices[:8]                       # 전부 무명이면 앞쪽만
        ev_dev = "\n".join(
            f"-{d['device'].lstrip('-')}" + (f" ({d['near']})" if d.get("near") else "")
            + f" — p{d['page']} {page_title.get(str(d['page']),'')}"
            for d in _dev) or "(회로도에서 수집된 부품 태그 없음)"
        # **쪽 전체 기기 제시(`--index-page-devices K`, P261)** — SL2500 v10e 의 남은 키워드는
        # 쪽 단위로 뭉쳐 빠진다(Q3 p32 의 -XS·SR2S11·SR2S12·-I035·X054·X055 전부, Q5 한 쪽의
        # -SQ25·26·28·-TM1·-CM1). 카탈로그 전체에서 몇 개를 고르는 한 이 묶음을 못 건진다.
        # 라우팅 상위 K 쪽에 **인덱스가 기록한 기기 전부**를 설명과 함께 근거로 보여 준다.
        # 보완 패스에 강제하지는 않는다(17개 이상 강제는 생성을 포화시켰다, P251).
        if args.index_page_devices:
            _blk = []
            # 연속 시트는 **판독만** 하고 기기 제시에는 넣지 않는다(v33: 제시에 넣자 핵심 쪽 기기가 묻혀 −3).
            for _pg in [x for x in func_pages if x not in _lay and x not in _cont][:args.index_page_devices] \
                    + (_cont if args.continuation_show else []) + _lay:
                _its = page2parts.get(str(_pg), [])
                if _its:
                    def _line(pt):
                        d_ = pt["description"]
                        # 쪽별 설명(그 쪽에서의 역할)에 **통합 부품의 모델·정격**을 덧붙인다(P274).
                        # v14 는 부품표 쪽(p11)이 우연히 상위 3쪽에 들어 모델이 보였고, v16 은 쪽별
                        # 설명만 보여 GV2ME·DRM570024LD 류를 잃었다(64.4 → 57.7).
                        g = sym.get(pt["symbol"]) or {}
                        mdl = [m for m in (g.get("models") or []) if m and m not in d_]
                        if not mdl:
                            _mm = re.search(r"\[([^\]]+)\]\s*$", g.get("description", ""))
                            if _mm and _mm.group(1) not in d_:
                                mdl = [_mm.group(1)]
                        if g.get("spec") and not mdl and g["spec"] not in d_:
                            mdl = [g["spec"]]
                        return f"- {pt['symbol']} = {d_}" + (f" [{'; '.join(mdl[:2])}]" if mdl else "")
                    _blk.append(f"[p{_pg} {page_title.get(str(_pg), '')} — 인덱스에 기록된 기기 {len(_its)}개]\n"
                                + "\n".join(_line(pt) for pt in _its[:args.index_page_devices_max]))
            if _blk:
                ev_dev = ev_dev + "\n\n" + "\n\n".join(_blk)
        # **코일 급전·직렬 접점(`--coil-feed`, P328).** 세 문서 심사(P327) 공통 결함: 접촉기 코일이
        # 어디서 전원을 받는지(SL2500 KM26 ← QM26 13-14 직결, DMU85 -B2-26Q61 ← ASi PWR AUX)를 안 쓴다.
        # 회로도 기록엔 있다 — 후보 기기(골라진 부품 + 상위 3쪽 기기)의 쪽별 기록 중 코일·보조접점
        # 줄만 모아 따로 보여 준다.
        _coil_lines = []
        if args.coil_feed:
            _cand = [str(t).upper().strip("-") for t in picked_parts]
            for _pg in func_pages[:3]:
                _cand += [str(pt.get("symbol", "")).upper().strip("-") for pt in page2parts.get(str(_pg), [])]
            _crx = re.compile(r"coil|13-14|13/14|\bA1\b|aux(iliary)? contact.*circuit|fed (from|via)|"
                              r"supply .* via|in series|series chain|PWR AUX"
                              + (r"|push.?button|self.?hold|re-?latch|power.?on|\bEON\b|machine on|ready (button|switch)"
                                 if args.operator_buttons else ""), re.I)
            _seen = set()
            for _t in dict.fromkeys(_cand):
                for _pg, _d in sym_pnotes.get(_t, []):
                    if _crx.search(str(_d)) and (_t, _d) not in _seen:
                        _seen.add((_t, _d))
                        _coil_lines.append(f"- -{_t} (p{_pg}): {str(_d)[:170]}")
                # **역방향(P331)** — DMU85 는 급전 정보가 **급전하는 기기** 쪽에 적혀 있다
                # ("-B2-23K11 … PWR AUX (UA/0VA) for -B2-26Q41"). 다른 기기 기록이 이 태그를 부르면 함께.
                for _o, _pg, _d in coil_rev.get(_t, []):
                    if (_o, _d) not in _seen:
                        _seen.add((_o, _d))
                        _coil_lines.append(f"- -{_o} (p{_pg}) → -{_t}: {str(_d)[:170]}")
            _coil_lines = _coil_lines[:25]
            if _coil_lines:
                ev_dev = ev_dev + "\n\n[코일 급전·직렬 접점 — 회로도 기록]\n" + "\n".join(_coil_lines)
        # **급전원 추적(`--feed-source N`, P352).** DMU85 캐비닛 쿨러: 쿨러 시트(p99)의 L 상은
        # "/B6-01.4 ← 3/L2/-X3-61" 로 들어오는데, 그 시트(p101)의 -B6-01Q21 출력이 급전원이다. 라우팅은
        # 쿨러 시트만 고르므로 보호기기가 근거에 없었다. 상위 쪽의 전위선(기호에 '/' + L·N·PE·L±)이
        # 가리키는 시트로 가서 같은 전위 행과 보호기기 행을 보여 준다. DIN 시트 참조 문서에서만 발화.
        _fs_tags, _fs_desc = [], {}         # `--feed-cover`(P363): 전위 행의 "from <기기>" — 부품 보완 강제 대상
        if args.feed_source:
            _fs, _seen_pg = [], set()
            _prx = re.compile(r"^\d*/?(\d/)?(L\d|N|PE|L\+|L-)\b|^\d/[A-Z]", re.I)
            _protx = re.compile(r"motor protect|protecting switch|circuit breaker|\bfuse|miniature|\bMCB\b|"
                                r"power supply unit|transformer|main switch", re.I)
            for _pg in func_pages[:3]:
                for _pt in page2parts.get(str(_pg), []):
                    _sy, _d = str(_pt.get("symbol", "")), str(_pt.get("description", ""))
                    if not _prx.search(_sy) or re.search(r"(^|/)(N|L-|PE|0V|GND)(/|$|\s)", _sy, re.I):
                        continue          # 귀선(N·L-·PE)은 급전원이 아니다 — 끝없이 이어져 근거만 채운다
                    for _code in re.findall(r"/([A-H]\d-\d{2})\.\d", _d):
                        for _sp in sorted(code2page.get(_code, ()), key=lambda x: int(x) if x.isdigit() else 0):
                            if _sp == str(_pg) or (_sp, _sy) in _seen_pg:
                                continue
                            _seen_pg.add((_sp, _sy))
                            _same = [f"- {sy} (p{pg}): {d[:170]}" for pg, sy, d in pdev_all
                                     if pg == _sp and sy == _sy]
                            _prot = [f"- {sy} (p{pg}): {d[:150]}" for pg, sy, d in pdev_all
                                     if pg == _sp and _protx.search(d) and not d.lower().startswith("parts list")]
                            _fs += [f"- {_sy} (p{_pg}) → 시트 {_code} (p{_sp})"] + _same + _prot[:3]
                            for _ln in _same:
                                for _t in re.findall(r"\bfrom (-[A-H]\d-\d{2}[A-Z]\d{2}|-[A-Z]{1,4}\d{1,4}[A-Z]?)\b", _ln):
                                    if _t not in _fs_tags:
                                        _fs_tags.append(_t)
                                        _fs_desc[_t] = "급전원: " + _ln[2:200]
            _fs = list(dict.fromkeys(_fs))[:args.feed_source]
            if _fs:
                ev_dev = ev_dev + "\n\n[급전원 — 이 회로의 전위선이 이어지는 시트의 전위·보호기기 기록]\n" + "\n".join(_fs)
        _acl = []
        if args.addr_circuit:
            for _, _, _a, _ in ranked[:args.addr_circuit]:
                _A = str(_a).upper()
                _m = re.fullmatch(r"([XYRFG])0*(\d+)\.(\d)", _A)
                _rx = re.compile(r"(?<![A-Z0-9_.])" + (f"{_m.group(1)}0?{_m.group(2)}\\.{_m.group(3)}" if _m
                                  else re.escape(_A)) + r"(?![0-9A-Z_])")
                _hits = [(pg, sy, d) for pg, sy, d in pdev_all
                         if _rx.search(d.upper()) or _rx.fullmatch(sy.upper().strip("-"))]
                # 그 주소 행 자신과 '구동/driven/lamp/relay' 를 말하는 줄을 먼저
                _hits.sort(key=lambda h: (not _rx.fullmatch(h[1].upper().strip("-")),
                                          not re.search(r"driv|relay|lamp|coil|direct|contact", h[2], re.I)))
                for pg, sy, d in _hits[:3]:
                    _acl.append(f"- {_a} (p{pg}) {sy}: {d[:150]}")
            _acl = _acl[:30]
            if _acl:
                ev_dev = ev_dev + "\n\n[회로도에서 이 신호가 실제로 연결된 기기 — I/O 맵 태그와 다르면 이쪽이 맞다]\n" + "\n".join(_acl)
        # **운전자 버튼 블록(`--button-block N`, P348).** DMU85 E-stop 리셋: Machine ON 버튼 -A7-01SH21 은
        # p60 인데 라우팅 상위 3쪽(59·61·30)에 없어 후보에 못 들었다. 버튼 기록은 문서당 6–17줄뿐이라
        # 리셋·전원·기동 질문이면 문서 전체에서 모아 보여 준다.
        # `--button-trigger-strict`(P353): '전원'·'켜' 단독은 오발화 — SL2500 x07 "자동 전원 차단", DMU85 Q2
        # "24V 제어전원", PUMA "작업등 안 켜져요" 에서 버튼 블록이 본문을 부풀렸다(x07 은 주소 Y27.4 날조까지).
        _btrig = (r"리셋|비상|시작|스타트|기동|준비|ready|reset|(전원|파워).{0,12}(안 들어|아무 반응|켜도|안 켜)|NC 화면"
                  if args.button_trigger_strict else r"리셋|전원|켜|안 들어|파워|비상|시작|스타트|기동|준비|ready|reset")
        if args.button_block and re.search(_btrig, q, re.I):
            _brx = re.compile(r"(button|push.?button|\bSB\w*|\bSH\d|\bSPB\d)", re.I)
            _bfx = re.compile(r"machine on|m/?c ready|machine ready|ready|reset|power.?on|power.?off|\bEON\b|\bEOF\b|"
                              r"control on|nc on|release", re.I)
            _bl = [f"- {sy} (p{pg}): {d[:150]}" for pg, sy, d in pdev_all
                   if _brx.search(sy + " " + d) and _bfx.search(d) and not d.lower().startswith("parts list")]
            _bl = list(dict.fromkeys(_bl))
            # `--button-first`(P349): 실물 버튼 태그(SB·SH·SPB·S##, 설명이 button/push…로 시작)를 앞으로.
            # v46 DMU85 리셋 답이 Machine ON 버튼을 안전 모듈 입력 -A3-01B11 I1 로 적었다(-A7-01SH21 이 실물).
            _hdr = "[운전자 버튼·자기유지 — 회로도 기록(문서 전체)]"
            if args.button_first:
                _phys = re.compile(r"^- -?(?:[A-Z]\d-\d{2})?(SB|SH|SPB|S)\d|^- \S+ \(p\d+\): (illuminated )?(push.?)?button", re.I)
                _bl.sort(key=lambda x: not _phys.search(x))
                _hdr = ("[운전자 버튼·자기유지 — 회로도 기록(문서 전체). 앞쪽이 운전자가 실제로 누르는 버튼 태그다 — "
                        "답에는 안전 모듈·PLC 입력 태그가 아니라 이 버튼 태그를 적는다]")
            _bl = _bl[:args.button_block]
            if _bl:
                ev_dev = ev_dev + "\n\n" + _hdr + "\n" + "\n".join(_bl)
        # **구동 신호 역추적(`--driver-signals N`, P331).** DMU85 유압: 신호 선택기가 "Clamping hydraulics"
        # (OX_HCD_ON)를 고르고 "Hydraulic on"(OX_GEN_HYD_ON)을 놓쳤는데, 후자의 상호참조 /B0-01.5 는
        # 이미 골라진 접촉기 -B0-01Q51 의 시트다. 골라진 부품 시트를 가리키는 신호를 근거로 보여 준다.
        _drv = []
        if args.driver_signals:
            _pp = set()
            for _t in picked_parts[:8]:
                for _c in (sym.get(_t, {}) or {}).get("sheets") or []:
                    _pp |= set(code2page.get(_c, ()))
            _have = {norm(a) for _, _, a, _ in ranked[:12]}
            for _a, _pgs in a2sheet.items():
                if _a not in _have and _pp & set(_pgs):
                    _drv.append(f"- {_a} | {', '.join(str(x) for x in a2l.get(_a, [])[:2])} | → p{','.join(_pgs[:2])}")
            _drv = _drv[:args.driver_signals]
            if _drv:
                ev_dev = ev_dev + "\n\n[골라진 부품의 시트를 가리키는 I/O 신호 — 도면 상호참조]\n" + "\n".join(_drv)
        _top = ranked[:min(args.must_top, len(ranked))]
        _must_pool = [a for _, _, a, _ in _top]
        if args.must_subsys:
            # ⚠ 규칙1 "아래 어드레스는 반드시 언급" 과 규칙6 "질문 계통 밖 신호는 쓰지 말 것"
            #   이 같은 프롬프트 안에서 정면충돌한다 — 강제 목록에 계통 밖 전역 신호가
            #   들어 있으면 모델은 규칙1을 따르고, 그래서 척 질문에 심압대 설명이 붙는다.
            #   강등 대상(전역)이면서 질문 계통과 무관한 것은 **강제 목록에서만** 뺀다
            #   (근거에서 지우지는 않는다 — 모델이 필요하면 쓸 수 있어야 한다).
            #   판정은 `demote_generic` 과 **같은 방식**이어야 한다: qrx 는 컴파일된
            #   정규식들의 **리스트**이고, 라벨은 ranked 튜플의 e["labels"] 에서 온다.
            _qrx = question_subsys(q)
            _keep = []
            for _sc, _kw, _a, _e in _top:
                if _a in GENERIC:
                    _lab = " ".join([str(_a)] + [str(x) for x in (_e.get("labels") or [])]).upper()
                    if not any(r.search(_lab) for r in _qrx):
                        continue
                _keep.append(_a)
            if _keep:
                if len(_keep) < len(_must_pool):
                    log.info(f"    강제 언급에서 계통 밖 전역 신호 {len(_must_pool)-len(_keep)}개 제외")
                _must_pool = _keep
        must = ", ".join(_must_pool)
        addrs = [a for _, _, a, _ in ranked]
        n_uncertain = sum(1 for _, _, a, _ in ranked if is_uncertain(conf.get(a, {})))

        report_progress("판독한 회로와 부품 정보를 바탕으로 답변을 작성하는 중",
                        f"정리한 신호 후보 {len(ranked)}개와 부품 후보 {len(picked_parts)}개를 바탕으로 초안을 작성합니다.\n"
                        "초안은 도면 출처 기록으로 다시 검토한 뒤 답변에 반영합니다.")
        ans = llm.chat(
            "CNC 전기회로 진단 전문가. **근거에 적힌 것 외에는 어드레스·신호명·부품을 지어내지 않는다.** "
            "라벨이 '(라벨 불확실)'이면 이름을 단정하지 말고 후보를 병기한다. " + CIRCUIT_RULES,
            f"질문: {q}\n\n[근거 — 질문 적합도·신뢰도 순 상위 {len(ranked)}개]\n{ev_top}\n\n"
            f"[설명 사전 — 어드레스별 신호명·해당 부품·회로 도면]\n{ev_explain}\n\n"
            f"[해당 회로도에 그려진 부품 — 캐비닛/현장에서 물리 점검할 대상]\n{ev_dev}\n\n"
            + (f"[관련 부품 — 이 질문에 맞춰 고른 것. 점검 순서에 넣을 것]\n"
               + ("\n".join(f"- {s} = {sym.get(s, {}).get('description', '')}"
                             for s in picked_parts) or "없음") + "\n\n"
               if args.parts_desc else
               f"관련 부품 태그: {', '.join(picked_parts) or '없음'}\n\n")
            + f"점검 순서를 단계별로 제시하세요. 규칙:\n"
            f"1) 아래 어드레스는 반드시 언급: {must}\n"
            + (f"1b) 설명 사전의 **[입력]/[출력]** 표시를 지켜서 쓰세요 — [출력]은 기계로 "
               f"나가는 명령이므로 \"신호가 나오는지/릴레이가 여자되는지\"로, [입력]은 "
               f"기계에서 들어오는 확인이므로 \"신호가 들어오는지/스위치가 닫히는지\"로 "
               f"서술합니다. 출력을 \"눌렸는지\"라고 쓰지 마세요.\n" if args.show_direction else "")
            + f"2) 각 어드레스는 **신호명과 함께** 인용하고, 설명 사전에 부품(-SP71 등)이 있으면 "
            f"   \"진단 화면에서 신호 확인 → 해당 부품의 물리 상태 점검(접점·LED·동작음)\" 순으로 "
            f"   쓰고, **회로도에서 수집된 부품 태그**를 점검 대상으로 명시할 것\n"
            f"   **무엇을 어떻게 볼지** 구체적으로 쓸 것\n"
            f"3) 회로 도면(p번호·제목)을 출처로 밝힐 것\n"
            f"4) 근거에 없는 어드레스·부품은 쓰지 말 것"
            + (f"\n5) **지령에서 부하까지 끝까지 따라갈 것.** 신호와 릴레이에서 멈추지 말고, "
               f"[회로도에 그려진 부품] 목록에서 그 계통의 **접촉기(-KM/-Q..)·모터보호스위치·"
               f"모터(-M..)·케이블**을 찾아 다음 순서로 쓰세요:\n"
               f"   지령(출력 어드레스) → 릴레이/모듈 → 접촉기 → 모터보호스위치/차단기 → 모터 → 배선\n"
               f"   그 계통 부품이 목록에 없으면 없다고 쓰고 지어내지 마세요.\n"
               f"6) **질문한 계통에 속하지 않는 신호는 쓰지 마세요.** 기계 전역 상태(비상정지·"
               f"기계 활성화·모드 선택·알람 램프)는 질문이 그것을 묻거나 그 계통의 인터록으로 "
               f"근거에 명시된 경우에만 쓰고, 서두나 말미에 습관적으로 나열하지 마세요.\n"
               if args.chain else "")
            + (_FULL_RULE if args.full_names else "")
            + (_PRIO_RULE if args.prioritize else "")
            + (_FEAS_RULE if args.feasible else "")
            + (_COIL_RULE if args.coil_feed else "")
            + (_BTN_RULE if args.operator_buttons else "")
            + (_POL2_RULE if args.polarity_rule2 else (_POL_RULE if args.polarity_rule else ""))
            + (_FEED_RULE if args.feed_source_rule else ""),
            max_new_tokens=args.max_tok, temperature=0.0)

        # **잘림 처리.** `pipeline/llm.py` 가 이제 finish_reason 을 남긴다. 상한에 걸렸으면
        # 한 번만 이어쓴다 — 무한 이어쓰기는 상투적 나열을 부추기므로 1회로 못박는다.
        _fin = getattr(llm, "last_finish_reason", None)
        _truncated = (_fin == "length")
        if _truncated and args.answer_continue:
            _cont = llm.chat(
                "CNC 전기회로 진단 전문가. 앞 답변의 **이어지는 부분만** 쓴다. 다시 시작하지 않는다. " + CIRCUIT_RULES,
                f"질문: {q}\n\n[여기까지 쓴 답변]\n{ans}\n\n"
                f"위 답변이 문장 중간에서 끊겼습니다. **끊긴 지점부터 이어서** 마무리하세요. "
                f"이미 쓴 내용을 반복하지 마세요.",
                max_new_tokens=args.max_tok, temperature=0.0)
            if _cont.strip():
                ans = ans.rstrip() + " " + _cont.strip()
            _truncated = (getattr(llm, "last_finish_reason", None) == "length")
            log.info(f"    답변이 잘려 이어썼다 (+{len(_cont)}자, 재잘림={_truncated})")
        elif _truncated:
            log.warning(f"    답변이 토큰 상한({args.max_tok})에서 잘렸다 — --answer-continue 미사용")

        # **부품 보완 패스** (성능 우선 — 생성 2회).
        # v6·v7a 실패 분해: 골라 준 부품이 답변에 안 나온 것(K4)이 8건. 토큰 상한을 1200→3000
        # 으로 풀어 잘림을 0/10 으로 만들었는데도 **K4 는 8건 그대로**였다 — 자리가 있어도
        # 안 쓴다. 그래서 답변을 낸 뒤 빠진 부품을 찾아, 설명과 함께 돌려주고 다시 쓰게 한다.
        _cov = {}
        # `--coverage-devices N`: 보완 대상에 **회로도에서 읽은 기능 있는 기기**도 넣는다.
        # SL2500 v8b 실패 분해: K5(근거엔 있었으나 답변 미언급) 17/66 — `-3SK11`·`-K01`·
        # `-SQ1` 이 [회로도에 그려진 부품] 에 있었는데 답변이 안 썼다. 무차별로 넣으면
        # '고정 필러 태그'(v29) 가 되므로 `near`(용도가 함께 읽힌 것)만, 최대 N개.
        _cov_dev = []
        if args.coverage_pass and args.coverage_devices:
            for d in _dev:
                t = "-" + d["device"].lstrip("-")
                if d.get("near") and t not in picked_parts and t not in _cov_dev:
                    _cov_dev.append(t)
            if args.cov_dev_rank:
                # **관련도 순(P260)** — 판독 순서대로 앞 N개를 쓰면 SL2500 Q8 에서 `-KA010..15`
                # (무관한 릴레이 줄)가 6칸을 먹었다. 질문 계통 정규식 + 고른 신호·부품 설명의
                # 토큰(`kws`)과 겹치는 기기만, 겹침 순으로.
                _qrx = question_subsys(q)
                _near = {"-" + d["device"].lstrip("-"): f"{d['device']} {d.get('near','')}" for d in _dev}
                _sc = {t: _relevance(_near.get(t, t), list(kws), _qrx) for t in _cov_dev}
                # 0점도 **버리지 않는다** — DMU85 는 기기 설명이 질문 토큰·계통 정규식과 거의
                # 안 겹쳐 대부분 0점이고, 버리면 v11 이 넣던 `-B7-04Q21/Q31` 을 잃었다(v13 −5.2pp).
                # 겹침 있는 것만 앞으로 당긴다(안정 정렬).
                _cov_dev = sorted(_cov_dev, key=lambda t: -_sc[t])
            _cov_dev = _cov_dev[:args.coverage_devices]
        if args.feed_cover and args.coverage_pass and _fs_tags:
            # v50 DMU85 쿨러: [급전원] 10줄·규칙 13 이 있어도 -B6-01Q21 을 안 썼다 → 보완 패스가 강제로 넣게.
            _cov_dev = [t for t in _fs_tags[:3] if t not in picked_parts] + [t for t in _cov_dev if t not in _fs_tags]
        _dnear = {"-" + d["device"].lstrip("-"): f"{d.get('near','')} — p{d['page']}" for d in _dev}
        if args.coverage_pass and (picked_parts or _cov_dev):
            _nrm = lambda s: re.sub(r"[^A-Z0-9]", "", str(s).upper())
            _miss0 = [s for s in list(picked_parts) + _cov_dev
                      if _nrm(s) and _nrm(s) not in _nrm(ans)]
            _cov = {"missing_before": _miss0, "rounds": []}
            # `--coverage-rounds N` / `--coverage-max M` (P260): 한 번에 12~14개를 돌려주면 일부만
            # 넣는다(SL2500 Q8: 12 → 8 남음, `-SVM5` 누락). 상한 M 개씩 N 번까지 반복한다.
            # 기본(1회·상한 없음)은 기존 동작과 같다.
            for _round in range(max(1, args.coverage_rounds)):
                _miss = [s for s in list(picked_parts) + _cov_dev
                         if _nrm(s) and _nrm(s) not in _nrm(ans)]
                if args.coverage_max:
                    _miss = _miss[:args.coverage_max]
                if not _miss:
                    break
                _desc = "\n".join(f"- {s} = {(_fs_desc.get(s) if args.feed_cover else None) or sym.get(s, {}).get('description', '') or _dnear.get(s, '')}"
                                   for s in _miss)
                _rev = llm.chat(
                    "CNC 전기회로 진단 전문가. **근거에 적힌 것 외에는 어드레스·신호명·부품을 "
                    "지어내지 않는다.** " + CIRCUIT_RULES,
                    f"질문: {q}\n\n[지금까지 쓴 답변]\n{ans}\n\n"
                    f"[해당 회로도에 그려진 부품]\n{ev_dev}\n\n"
                    f"[답변에 빠진 관련 부품 — 이 질문에 맞춰 골라진 것]\n{_desc}\n\n"
                    f"위 부품들이 답변에 없습니다. 각 부품이 점검 순서의 어느 단계에 들어가는지 "
                    f"판단해 **답변 전체를 다시** 쓰세요. 기존 답변의 단계·어드레스·신호명은 "
                    f"**모두 유지**하고, 빠진 부품을 알맞은 단계에 태그 그대로 넣으세요. "
                    f"이 고장과 정말 무관한 부품은 넣지 마세요."
                    + (_FULL_RULE if args.full_names else "")
                    + (_PRIO_RULE if args.prioritize else "")
                    + (_FEAS_RULE if args.feasible else "")
            + (_COIL_RULE if args.coil_feed else "")
            + (_BTN_RULE if args.operator_buttons else "")
            + (_POL2_RULE if args.polarity_rule2 else (_POL_RULE if args.polarity_rule else ""))
            + (_FEED_RULE if args.feed_source_rule else ""),
                    max_new_tokens=args.max_tok, temperature=0.0)
                # 모델이 전체가 아니라 덧붙일 부분만 돌려주면 기존 답을 잃는다 — 너무 짧으면 버린다.
                _acc = len(_rev.strip()) >= 0.8 * len(ans.strip())
                if _acc:
                    ans = _rev.strip()
                _left = [s for s in _miss if _nrm(s) not in _nrm(ans)]
                _cov["rounds"].append({"asked": _miss, "left": _left, "accepted": _acc})
                _cov["accepted"] = _acc
                _cov["missing_after"] = _left
                log.info(f"    부품 보완[{_round + 1}]: 빠짐 {len(_miss)} → {len(_left)} (채택={_acc})")
                if not _acc:
                    break

        # **주소 검증 패스(`--validate-addrs`, P301).** 심사 4회 모두 같은 날조를 지적했다 — 도면에 없는
        # 주소 표기(`R1.0`·`X90.0`·`X15.4`: 릴레이 접점 R1–R6, 배선번호 X090, 교차참조 X015 를
        # 주소로 옮겨 씀). 답변에서 주소 모양 토큰을 뽑아 인덱스에 없는 것만 돌려주고, 근거에 있는
        # 올바른 주소로 바꾸거나 지우게 한다. 짧아지면(0.8×) 버린다.
        _val = {}
        if args.validate_addrs:
            _known = {norm(k) for k in a2l}
            # 인덱스가 불완전한 문서(PUMA: X05.6/7·X06.x·X08.2/3 미전사, P313)에서 실제 주소를
            # 지우지 않도록 **근거 텍스트(판독·설명·기기)에 나온 주소**도 존재하는 것으로 본다.
            # 단, **인덱스에 있는 주소 계열(X/Y …)만** — SL2500 은 VLM 이 바 피더 릴레이 접점 R2–R6 을
            # `R2.0` 으로 읽어 근거에 넣었고, 이것까지 인정하자 v36 이 R2.0–R6.0 날조를 되살렸다(P319).
            _pfx = {k[:1] for k in _known}
            _known |= {norm(t) for t in re.findall(r"(?<![A-Za-z0-9_])[XYRFG]\d{1,3}\.\d(?![0-9])",
                                                   f"{ev_top}\n{ev_explain}\n{ev_dev}")
                       if norm(t)[:1] in _pfx}
            _toks = set(re.findall(r"(?<![A-Za-z0-9_])[XYRFG]\d{1,3}\.\d(?![0-9])", ans))
            _bad = sorted(t for t in _toks if norm(t) not in _known)
            _val = {"bad": _bad}
            if _bad:
                _fix = llm.chat(
                    "CNC 전기회로 진단 전문가. **근거에 적힌 것 외에는 어드레스를 지어내지 않는다.**",
                    f"질문: {q}\n\n[답변]\n{ans}\n\n[근거 — 실제 존재하는 어드레스]\n{ev_top}\n\n"
                    f"[설명 사전]\n{ev_explain}\n\n"
                    f"답변의 다음 어드레스는 **이 도면의 I/O 목록에 없습니다**: {', '.join(_bad)}\n"
                    f"(릴레이 접점 번호·배선 번호·교차참조 좌표를 어드레스로 잘못 옮긴 경우가 많습니다.) "
                    f"각각을 근거에 있는 올바른 어드레스로 바꾸거나, 대응을 모르면 어드레스 없이 부품·배선 "
                    f"이름으로만 쓰세요. 나머지 내용은 **그대로 유지**하고 답변 전체를 다시 쓰세요.",
                    max_new_tokens=args.max_tok, temperature=0.0)
                _ok = len(_fix.strip()) >= 0.8 * len(ans.strip())
                if _ok:
                    ans = _fix.strip()
                _val["accepted"] = _ok
                _val["left"] = sorted(t for t in set(re.findall(
                    r"(?<![A-Za-z0-9_])[XYRFG]\d{1,3}\.\d(?![0-9])", ans)) if norm(t) not in _known)
                log.info(f"    주소 검증: 없는 주소 {len(_bad)} → {len(_val['left'])} (채택={_ok})")
        # **정리 패스(`--prune`, P312).** gold 대비 블라인드 심사(P310): 우리 답은 환각은 gold 수준인데
        # 본문 무관 항목이 문항당 5–6개(gold 0), 부품 역할 오기가 1.1–1.2개(gold 0.3–0.4)였다.
        # 보완 패스가 재현율을 올리며 본문을 채운 결과다. 답에 나온 태그의 인덱스 설명을 주고
        # ① 설명과 어긋난 역할을 고치고 ② 원인 경로 밖 항목은 [참고] 로 **옮기게** 한다(삭제 금지).
        # 태그가 3개 이상 사라지거나 0.7× 보다 짧아지면 버린다.
        _prn = {}
        if args.prune:
            _U = ans.upper()
            _tags = [k for k in sym if len(str(k).strip("-")) >= 2 and re.search(
                r"(?<![A-Z0-9])" + re.escape(str(k).strip("-").upper()) + r"(?![A-Z0-9])", _U)]
            _tags = sorted(set(_tags), key=lambda k: _U.find(str(k).strip("-").upper()))[:45]
            def _role(k):
                _pn = sym_pnotes.get(str(k).upper().strip("-"), [])
                _pn = sorted(_pn, key=lambda x: (x[0] not in func_pages, x[0]))[:3]
                # 회로도 쪽 기록을 **먼저**, 통합(부품표 포함) 설명은 참고로 — DMU85 부품표는 접촉기
                # `-Q51` 을 "power circuit breaker" 라 적어 v35 가 역할을 그쪽으로 '교정'했다(P316).
                _rv = coil_rev.get(str(k).upper().strip("-"), [])[:2] if args.verify_links else []
                return (f"- {k}" + "".join(f"\n    · 회로도 p{pg}: {str(d)[:140]}" for pg, d in _pn)
                        + "".join(f"\n    · 회로도 p{pg} (-{o}): {str(d)[:140]}" for o, pg, d in _rv)
                        + f"\n    · 부품표/통합: {str(sym[k].get('description', ''))[:140]}")
            _roles = "\n".join(_role(k) for k in _tags)
            _tagtok = lambda t: {str(k).strip("-").upper() for k in _tags if re.search(
                r"(?<![A-Z0-9])" + re.escape(str(k).strip("-").upper()) + r"(?![A-Z0-9])", t.upper())}
            _before = _tagtok(ans)
            _pr = llm.chat(
                "CNC 전기회로 진단 전문가. 정비사가 바로 따라 할 수 있는 답을 쓴다. "
                "**근거에 없는 어드레스·신호·부품은 지어내지 않는다.** " + CIRCUIT_RULES,
                f"질문: {q}\n\n[답변 초안]\n{ans}\n\n"
                f"[답변에 나온 부품의 도면 설명 — 역할의 기준]\n{_roles}\n\n"
                f"초안을 다음 규칙으로 **다듬어 전체를 다시** 쓰세요.\n"
                f"1) 각 부품의 역할을 위 도면 설명과 대조하세요. 설명과 다른 역할로 쓴 곳(다른 계통의 "
                f"보호기·접촉기를 이 계통 것으로 쓴 경우 등)은 설명에 맞게 고치세요. **회로도 쪽 기록이 "
                f"부품표 설명보다 정확합니다** — 둘이 다르면 회로도 기록을 따르고, 확실하지 않으면 초안을 "
                f"그대로 두세요. 원인 경로에 있는 부품을 빼지 마세요.\n"
                f"2) 본문에는 **이 고장의 원인 경로에 직접 속한 항목만** 순서대로 남기세요: 지령(출력) → "
                f"릴레이/모듈 → 접촉기(코일이 어디서 전원을 받는지 포함) → 보호기/차단기 → 모터·밸브·센서 "
                f"→ 배선. 같은 페이지에 있을 뿐 이 고장과 무관한 신호·릴레이·램프는 본문에서 빼서 맨 끝 "
                f"**[참고 — 같은 도면의 관련 기기]** 절로 **옮기세요(지우지 말 것)**.\n"
                f"3) 새 태그·어드레스·신호를 추가하지 말고, 태그 표기는 그대로 쓰세요.\n"
                f"4) 위 쪽별 기록에 접촉기 코일 회로의 직렬 접점(보호기 보조접점 13-14 등)이나 전원선이 "
                f"있으면 해당 단계에 **그 접점·선 이름을 명시**하세요.\n"
                f"5) 답변 끝에 [근거]·[설명 사전] 같은 입력 블록을 복사하지 마세요."
                + ("\n6) **연결 주장 검증**: 초안이 'A 가 B 를 구동한다', 'A 의 접점이 B 코일에 직렬', "
                   "'A 에서 급전' 처럼 두 기기의 연결을 말하면, 위 회로도 기록에 그 연결이 있는지 확인하세요. "
                   "기록에 없는 연결은 지우고 두 기기를 각각 점검 대상으로만 남기세요." if args.verify_links else "")
                + (_FULL_RULE if args.full_names else ""),
                max_new_tokens=args.max_tok, temperature=0.0)
            _after = _tagtok(_pr)
            _lost = sorted(_before - _after)
            _ok = len(_pr.strip()) >= 0.7 * len(ans.strip()) and len(_lost) <= 2
            _prn = {"tags": len(_before), "lost": _lost, "accepted": _ok,
                    "len": [len(ans), len(_pr)]}
            if _ok:
                ans = _pr.strip()
            log.info(f"    정리 패스: 태그 {len(_before)} · 잃음 {len(_lost)} · "
                     f"길이 {_prn['len'][0]}→{_prn['len'][1]} (채택={_ok})")
        # **입력 블록 누출 제거(P316).** 재작성 패스가 프롬프트의 `[근거 — 실제 존재하는 어드레스]`·
        # `[설명 사전]` 블록을 답 끝에 그대로 복사한 사례(SL2500 Q9, 1,600자). 줄 머리의 헤더부터 자른다.
        if args.prune:
            _cut = re.search(r"(?m)^\s*\**\s*\[(근거|설명 사전|해당 회로도에 그려진 부품|답변에 빠진|코일 급전|골라진 부품|회로도에서 이 신호)[^\]]*\]\s*\**\s*$", ans)
            if _cut:
                ans = ans[:_cut.start()].rstrip()
                _prn["leak_cut"] = True
        # **태그 검증(`--validate-tags`, P342).** DMU85 심사가 반복 지적한 날조 태그(-A7-02K11 = 교차참조
        # "/A7-02.1" 을 기기로, -A5-15T31·-C1-18K41)는 인덱스에 없다. DIN 형식만 본다 — 짧은 태그는
        # 핀·범위 표기("X6.0-Y3")와 섞여 오탐이 많았다(v42 재현: FANUC 두 문서 25건 중 대부분 오탐).
        _tv = {}
        if args.validate_tags:
            _known_t = {str(k).upper().strip("-") for k in sym} | {
                str(sy).upper().strip("-") for _, sy, _ in pdev_all}
            _bt = sorted({t for t in re.findall(r"(?<![A-Za-z0-9_/.])-([A-Z]\d-\d{2}[A-Z]{1,2}\d{2})(?![A-Za-z0-9_])", ans)
                          if t.upper() not in _known_t})
            _tv = {"bad": _bt}
            if _bt:
                _fx = llm.chat(
                    "CNC 전기회로 진단 전문가. **근거에 적힌 것 외에는 기기 태그를 지어내지 않는다.**",
                    f"질문: {q}\n\n[답변]\n{ans}\n\n[근거 — 회로도에 그려진 기기]\n{ev_dev}\n\n"
                    f"답변의 다음 기기 태그는 **이 도면에 없습니다**: {', '.join('-' + t for t in _bt)}\n"
                    f"(교차참조 좌표 '/A7-02.1' 같은 것을 기기 태그로 잘못 옮긴 경우가 많습니다.) 각각을 근거에 있는 "
                    f"올바른 태그로 바꾸거나, 모르면 그 언급을 지우세요. 나머지는 **그대로 유지**하고 답변 전체를 다시 쓰세요.",
                    max_new_tokens=args.max_tok, temperature=0.0)
                _ok = len(_fx.strip()) >= 0.8 * len(ans.strip())
                if _ok:
                    ans = _fx.strip()
                    _c2 = re.search(r"(?m)^\s*\**\s*\[(근거|설명 사전)[^\]]*\]\s*\**\s*$", ans)
                    if _c2:
                        ans = ans[:_c2.start()].rstrip()
                _tv["accepted"] = _ok
                log.info(f"    태그 검증: 없는 태그 {len(_bt)} (채택={_ok})")
        # **메타 문장 제거(`--meta-cut`, P349).** 재작성 패스가 지시문에 답하는 문장을 본문에 남긴 사례
        # (v46 DMU85 Q9 "(참고: 요청하신 대로 근거에 없는 … 태그는 검토 결과 도면에 존재하지 않으므로…)").
        if args.meta_cut:
            _mrx = re.compile(r"요청하신|검토 결과|근거에 없는|도면에 존재하지 않|근거에 (나와|제시되어) ?있지 않|지어내지")
            _ml = [ln for ln in ans.split("\n") if _mrx.search(ln)]
            if _ml:
                ans = "\n".join(ln for ln in ans.split("\n") if not _mrx.search(ln))
                _tv["meta_cut"] = len(_ml)
        ar = addr_recall(ans, gaddr)
        if ar["recall"] is not None:
            recs.append(ar["recall"])
        # **추적 기록** — 사람이 답을 검증하려면 "어느 인덱스를 골랐고 그것이 도면 어느
        # crop에서 왔고 거기서 어디로 이어졌는지"가 남아 있어야 한다. 지표에는 영향이 없고
        # 파일만 커진다. `scripts/build_trace_html.py`가 이 필드로 crop을 복원해 보여 준다.
        trace = {
            "signals": [{"name": nm, "addrs": [[a, pg] for a, pg in ad]} for nm, ad in by_sig],
            "sig_hits": sig_hits,
            "routing": {"parts": tr_parts, "titles": tr_titles, "sheet_refs": tr_refs,
                        "score": {p: round(v, 3) for p, v in
                                  sorted(score.items(), key=lambda kv: (-kv[1], int(kv[0])))[:12]},
                        "cand_pages": {p: v for p, v in
                                       sorted(cand_pages.items(),
                                              key=lambda kv: (-kv[1], int(kv[0])))[:12]}},
            "read": [{k: v for k, v in e.items() if k in
                      ("address", "page", "labels", "src", "from")} for e in found],
            "devices": devices,
            "shown_devices": [d["device"] for d in _dev],
            "ranked": [{"rank": _i + 1, "address": _a, "score": round(_s, 3), "kw": _kw,
                        "src": _e.get("src"), "page": _e.get("page"),
                        "labels": _e.get("labels", []), "from": _e.get("from", []),
                        "conf": conf.get(_a, {}),
                        "uncertain": is_uncertain(conf.get(_a, {}))}
                       for _i, (_s, _kw, _a, _e) in enumerate(ranked)],
            "explain": ex_lines,
            "must": must.split(", ") if must else [],
            # 잘림은 **기록으로** 남긴다. 로그 줄만 남기면 나중에 "몇 개가 잘렸나"를
            # 셀 수 없고, 잘린 답과 짧은 답이 채점에서 구분되지 않는다.
            "finish_reason": _fin,
            "truncated": bool(_truncated),
            "rev_pages": rev_pages,
            "coverage": _cov,
            "page_parts_added": _pp_added,
            "addr_validation": _val,
            "prune": _prn,
            "tag_validation": _tv,
            # 근거 블록 발화 기록(P358): "효과 없음" 전에 발화 여부부터 — 블록 머리글별 줄 수
            "ev_blocks": {m.group(1)[:24]: len(m.group(2).strip().splitlines())
                          for m in re.finditer(r"\n\[([^\]\n]{4,80})[^\n]*\n((?:- .*\n?)+)", ev_dev)},
        }
        rows.append({"id": it.get("id"), "question": q, "gold_addr": gaddr,
                     "gold_answer": it.get("answer", ""), "picked_parts": picked_parts,
                     "picked_signals": picked_sigs, "func_pages": func_pages,
                     "rev_pages": rev_pages,
                     "page_titles": [page_title.get(p, "") for p in func_pages + rev_pages],
                     "evidence": ev_top.split("\n"), "n_uncertain": n_uncertain,
                     "read_addrs": addrs, "devices": [d["device"] for d in devices],
                     "trace": trace, "answer": ans, "addr": ar})
        log.info(f"[{i+1}/{len(qa)}] {it.get('id')}: func p{func_pages} rev p{rev_pages} "
                 f"| 총 {len(addrs)}개 | recall={ar['recall']} matched={ar.get('matched')}")

    n = len(rows)
    tot_g = sum(len(r["gold_addr"]) for r in rows)
    tot_h = sum(len(r["addr"].get("matched") or []) for r in rows)
    tot_p = sum(len(r["read_addrs"]) for r in rows)
    summary = {"n": n, "addr_recall_pct": round(100*sum(recs)/len(recs), 1) if recs else None,
               "micro_recall_pct": round(100*tot_h/max(1, tot_g), 1),
               "avg_proposed_addrs": round(tot_p/max(1, n), 1),
               "efficiency_per_1000": round(1000*tot_h/max(1, tot_p), 1),
               "func_pages": args.func_pages, "rev_pages": args.rev_pages, "scale": args.scale,
               "elapsed_sec": round(time.time()-t0, 1),
               "docid": args.docid or "puma280", "model": os.environ.get("LLM_NAME", "gemma4"),
               "pdf": str(pdf), "cache": str(_CACHE), "qa": str(args.qa),
               "titles": args.titles, "explain": args.explain, "io_rows": args.io_rows,
               "index_sig": {k: _index_sig(getattr(args, k, ""))
                             for k in ("explain", "io_rows", "io")},
               "render_dir": args.render_dir,
               "note": "v6 — 근거 재순위(상위 N) + 라벨 신뢰도(불확실 표시) + 인용 강제. 부록 나열 없음"}
    Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows},
                                         ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    log.info(f"wrote {args.out}")
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
