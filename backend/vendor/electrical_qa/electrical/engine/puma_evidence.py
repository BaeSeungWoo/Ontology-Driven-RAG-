"""근거 재순위 + **라벨 신뢰도** — 잘못된 OCR 라벨을 안전하게 다루기 위한 모듈.

측정된 사실(RESEARCH_LOG P45): I/O MAP 라벨 정확도는 판정 가능분 중 **42%**였고,
오류에는 뚜렷한 서명이 있다 — **연속 어드레스가 같은 라벨을 받는다**(행/비트 정렬 밀림):
  `X33.2·X33.6·X33.7 → 전부 FEED HOLD`(정답 HDZ.M / ST.M / SP.M),
  `X9.5·X9.6 → 전부 SPEED CONFIRM`(정답 LUB. LEVEL / LUB. PRESSURE).
밴드를 10개로 얇게 하면 교정되지만(ST.M·SP.M·HDZ.M 정상 판독), 남는 오류는 있다.

그래서 라벨을 **믿을지 말지 판정**하고, 못 믿을 때는 단정하지 않는다:
  1) 반복 라벨 감지 — 한 라벨이 3개 이상 어드레스를 덮으면 정렬 밀림 의심 → 신뢰도 하락
  2) 교차 출처 합의 — 여러 인덱스(I/O MAP·신호시트·회로도 판독)가 같은 라벨을 주면 신뢰도 상승
  3) 불확실 표시 — 신뢰도 낮으면 답변에 "(라벨 불확실)"로 표기, 이름을 단정하지 않음
  4) 라벨에만 의존하지 않기 — 부품 라우팅·어드레스 역라우팅을 병행해 라벨이 틀려도 도달 가능
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

ADDR_NORM = re.compile(r"([XYRGFKT])0*(\d+)\.(\d)")


def norm(a):
    return ADDR_NORM.sub(r"\1\2.\3", str(a).strip().upper())


def label_confidence(entries):
    """(address → {label: score}) + 라벨별 신뢰 판정.

    entries: [{"address","labels","page","src"}...] 여러 출처가 섞여 있어도 된다.
    """
    lab_cover = Counter()          # 라벨이 덮는 서로 다른 어드레스 수 (많으면 정렬 밀림 의심)
    per_addr = defaultdict(lambda: defaultdict(set))   # addr -> label -> {src}
    for e in entries:
        a = norm(e["address"])
        for l in e.get("labels", []) or []:
            if l:
                per_addr[a][l].add(e.get("src", "?"))
    for a, labs in per_addr.items():
        for l in labs:
            lab_cover[l] += 1
    out = {}
    for a, labs in per_addr.items():
        scored = {}
        for l, srcs in labs.items():
            s = 1.0
            s += 0.6 * (len(srcs) - 1)              # 교차 출처 합의 보너스
            if lab_cover[l] >= 3:                   # 반복 라벨 → 정렬 밀림 의심
                s -= 0.8
            if re.fullmatch(r"[A-Z]{1,4}\d*\.?[A-Z]?", l.strip()):
                s += 0.1                            # 약어 코드(ST.M 등)는 도면 표기와 일치
            scored[l] = round(s, 2)
        out[a] = scored
    return out, lab_cover


def is_uncertain(scored_labels, thresh=0.6):
    """최고 점수가 낮거나 상위 두 라벨이 팽팽하면 불확실."""
    if not scored_labels:
        return True
    ranked = sorted(scored_labels.items(), key=lambda kv: -kv[1])
    if ranked[0][1] < thresh:
        return True
    if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.2:
        return True
    return False


SRC_PRIOR = {"IO": 3.0, "REV": 1.0, "DWG": 0.5}


def rank_evidence(entries, keywords, conf, kind=None, top=10):
    """출처 사전순위 + 질문 키워드 적합도 + 라벨 신뢰도로 재순위화.

    P47 교훈: 키워드 일치에만 의존해 상위 10개로 자르면 **gold의 2/3가 잘려나간다**
    (근거풀 64.7% → 재순위 후 20.6%). 라벨이 틀리거나 없는 어드레스는 키워드 점수가 0이라
    밀리기 때문. 그래서 **질문으로 고른 신호에서 온 근거(IO)는 구조적으로 관련**이므로
    강한 사전순위를 준다.
    """
    seen, ranked = set(), []
    for e in entries:
        a = norm(e["address"])
        if a in seen:
            continue
        seen.add(a)
        scored = conf.get(a, {})
        best = max(scored.values()) if scored else 0.0
        labs = " ".join(scored.keys()).upper()
        kw = sum(1 for k in keywords if k and k in labs)
        # 라벨을 못 읽은 어드레스는 kw·best가 0이라 최하점이 된다. 그런데 **질문으로 라우팅된
        # 바로 그 시트에서 읽힌 어드레스는 라벨이 없어도 강한 근거**다(척 정답 Y0.6·Y0.7이
        # `p75 MAIN CHUCK CONTROL`에서 읽혔는데 라벨 판독 실패로 15·16위까지 밀린 사례).
        # → DWG/REV는 고정 prior 대신 **시트 관련도(page_prior)** 를 더한다.
        base = SRC_PRIOR.get(e.get("src", "DWG"), 0.5)
        if e.get("src") in ("DWG", "REV"):
            base += float(e.get("page_prior", 0.0))
        s = base + 2.0 * kw + 0.5 * best
        if kind and a.startswith(kind):
            s += 0.5                                  # 질문 의도(입력 X / 출력 Y) 가산
        ranked.append((s, kw, a, e))
    ranked.sort(key=lambda x: -x[0])
    return ranked[:top]


def rank_evidence_quota(entries, keywords, conf, kind=None, top=16, quota=None):
    """**출처별 쿼터** 선택 — 두 트랙이 서로 다른 문항을 담당하므로 한 순위로 경쟁시키지 않는다.

    P48 교훈: 단일 순위 + IO 사전순위(3.0)로 뽑으니 IO가 회로도 판독(0.5)을 눌러,
    v4에서 회로도로 맞히던 문항(칩컨베이어 p31 · 척 p75 · 터렛 p105)이 통째로 밀려났다.
    반대로 IO 트랙은 cycle-start·윤활을 살렸다. → 각 출처에서 상위 N개씩 **따로** 뽑는다.
    """
    quota = quota or {"IO": top // 2, "DWG": top // 2, "REV": max(2, top // 4)}
    by_src = {}
    for s, kw, a, e in rank_evidence(entries, keywords, conf, kind=kind, top=10 ** 6):
        by_src.setdefault(e.get("src", "DWG"), []).append((s, kw, a, e))
    picked, seen = [], set()
    for src, lim in quota.items():
        for item in by_src.get(src, [])[:lim]:
            if item[2] not in seen:
                seen.add(item[2]); picked.append(item)
    picked.sort(key=lambda x: -x[0])
    return picked[:top]


def _descriptive(label):
    """서술형 이름(TAILSTOCK FOOT SWITCH)을 약어(LS1.M)·코드((SM1))·번호(27)보다 우선.

    P64: 척 `X11.4`의 라벨은 `['LS1.M','(SM1)','TAILSTOCK FOOT SWITCH']`였는데 상위 2개만
    표시돼 gold의 FOOT SWITCH가 생성기에 보이지 않았다. 후보 정렬 시 서술형에 가산한다."""
    l = str(label).strip()
    if re.fullmatch(r"\(?\d+\)?", l):
        return -2.0                                    # 셀 번호(27, 11)
    if re.fullmatch(r"\(?[A-Z]{1,4}\d{0,4}[A-Z]?\.?[A-Z]?\)?", l):
        return -0.5                                    # 약어/부품코드(LS1.M, (SM1))
    return 1.0 + 0.1 * min(len(l.split()), 5)          # 서술형(단어 수만큼 가산)


# 셀번호(`27`)·격자좌표(`A02`)·한 글자 조각은 이름이 아니다. 실측: 근거의 후보 라벨
# 477개 중 91개(19%)가 이것들이었고, 답변에 "(라벨 불확실) 후보: … 또는 A02" 형태로 노출돼
# 신뢰를 깎았다. **표시 단계에서만** 거른다 — `label_confidence`/`rank_evidence`의 입력을
# 건드리면 `lab_cover`가 바뀌어 순위가 망가진다(v13a: recall 50.0→44.1%).
JUNK_LABEL = re.compile(r"^\(?(?:\d{1,3}|[A-Z]\d{1,2}|[A-Z]|M)\)?$")


def _display_labels(scored):
    """표시용 후보만 남긴다(무의미 토큰 제거). 전부 무의미하면 원본을 그대로 쓴다."""
    labs = sorted(scored.items(), key=lambda kv: -(kv[1] + _descriptive(kv[0])))
    keep = [(l, v) for l, v in labs if not JUNK_LABEL.match(str(l).strip())]
    return keep or labs


def format_evidence(ranked, conf, page_title=None, clean=True):
    """생성기에 줄 근거 문자열 — 불확실한 라벨은 단정하지 않는다."""
    page_title = page_title or {}
    lines = []
    for s, kw, a, e in ranked:
        scored = conf.get(a, {})
        labs = (_display_labels(scored) if clean else
                sorted(scored.items(), key=lambda kv: -(kv[1] + _descriptive(kv[0]))))
        if not labs:
            desc = "(라벨 판독 실패 — 이름 단정 금지)"
        elif is_uncertain(scored):
            desc = "(라벨 불확실) 후보: " + " 또는 ".join(l for l, _ in labs[:3])
        else:
            desc = labs[0][0] + (f" (후보: {labs[1][0]})" if len(labs) > 1 else "")
        pg = str(e.get("page", ""))
        lines.append(f"{a} | {desc} | p{pg} {page_title.get(pg, '')}")
    return "\n".join(lines) or "(근거 없음)"
