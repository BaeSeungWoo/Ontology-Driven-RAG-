"""PUMA 회로도 페이지 검색 v2 — S1: 스코어 정규화 + off-type 패널티.

진단(results/RESEARCH_LOG.md §6-P1): 기존 lookup은 매칭 signal **raw count**로 페이지를
점수화해 11개 질문 중 6개가 동일 페이지(54,126,71,114)로 붕괴. 원인 3가지를 각각 처리한다.

  (a) 중복 entry 폭증  : p114는 190 entries인데 고유 어드레스 1개 → **고유 어드레스로 집계**
  (b) popularity bias  : 어드레스 밀집 페이지가 질문 무관하게 1위 → **IDF 가중 + 길이 정규화**
                         (806/865 signal이 단일 페이지에만 존재 = IDF 변별력 매우 큼)
  (c) off-type 페이지  : PARTS LIST(p126)·배선 레이아웃(p71) → **타입 감점**
                         Blueprint(arXiv 2602.13345)의 s_final = s_λ + α·match − γ·off-type

주의: 밀집 페이지가 전부 나쁜 게 아니다 (p54·p19·p60·p115는 밀집이면서 oracle).
그래서 길이 정규화는 β로 조절 가능하게 두고(β=0이면 미적용), 타입 감점과 분리한다.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

ADDR_NORM = re.compile(r"([XYRGFKT])0*(\d+)\.(\d)")


def norm_addr(a: str) -> str:
    return ADDR_NORM.sub(r"\1\2.\3", str(a).strip().upper())


# ---------- 페이지 타입 (텍스트 마커 기반) ----------
# 정답 페이지(p115=커넥터 레이아웃이지만 Y3.x 정답 보유)를 죽이지 않도록,
# 감점은 '부품 카탈로그'처럼 어드레스가 답이 될 수 없는 타입에만 강하게 준다.
TYPE_RULES = [
    ("parts_list", re.compile(r"P\s*A\s*R\s*T\s*S\s+L\s*I\s*S\s*T|DESCR\s*I?\s*PT|SPEC\s*IF\s*ICATIO", re.I)),
    ("io_table", re.compile(r"I\s*/\s*[O0]\s*[1lNI][-]?[AI4]ME|SLOT|MODULE", re.I)),
    ("index", re.compile(r"CONTENTS|INDEX|DRAWING\s+LIST", re.I)),
]


def classify_pages(chunks_df) -> dict[str, str]:
    """페이지 → 타입. 마커가 없으면 circuit(회로도)."""
    out = {}
    for pr, sub in chunks_df.groupby(chunks_df["page_range"].astype(str)):
        txt = " ".join(str(t) for t in sub["text"])
        t = "circuit"
        for name, pat in TYPE_RULES:
            if pat.search(txt):
                t = name
                break
        out[str(pr)] = t
    return out


class LookupIndex:
    """page_index.json entries에서 검색용 통계를 미리 계산."""

    def __init__(self, entries, chunks_df=None, min_sig_ratio=0.0, max_addr_per_signal=0):
        """min_sig_ratio: 페이지의 (고유 signal 수 / 고유 address 수)가 이 값 미만이면 제외.

        full-page VLM-OCR이 어드레스 공간을 **열거 환각**한 페이지를 걸러낸다. 예: p54는
        어드레스 214개(27워드 중 26워드가 8비트 전부)에 signal이 'EMG' 하나뿐 = 도면에서
        읽은 게 아니라 X0.0~X17.7을 생성한 것. 이런 페이지가 검색을 지배하고 답변 나열을
        부풀렸다. 비율 0.5 기준으로 13/62 페이지가 걸러지며 gold 커버는 100%(환각 포함)에서
        **69%(정직)**로 내려간다."""
        if min_sig_ratio > 0:
            stat = defaultdict(lambda: [set(), set()])
            for e in entries:
                p = str(e["page"])
                stat[p][0].add(norm_addr(e["address"]))
                stat[p][1].add(str(e["signal"]).upper())
            keep = {p for p, (a, s) in stat.items() if len(s) / max(1, len(a)) >= min_sig_ratio}
            entries = [e for e in entries if str(e["page"]) in keep]
        if max_addr_per_signal:
            # **entry 단위 정화**(페이지 단위보다 정확). 환각의 서명은 "이름 하나가 수십
            # 어드레스를 덮는 것"이다. 페이지 단위로 자르면 p19처럼 184개 중 대부분이 열거여도
            # 정확한 짝(CYCLE START=X33.6)까지 함께 버려진다. 그래서 (page, signal)이 덮는
            # 어드레스가 임계치를 넘는 entry만 버린다.
            cover = defaultdict(set)
            for e in entries:
                cover[(str(e["page"]), str(e["signal"]).upper())].add(norm_addr(e["address"]))
            entries = [e for e in entries
                       if len(cover[(str(e["page"]), str(e["signal"]).upper())]) <= max_addr_per_signal]
        self.entries = entries
        self.page_addrs = defaultdict(set)      # page -> 고유 어드레스
        self.sig_pages = defaultdict(set)       # signal -> 등장 페이지 (IDF용)
        self.page_sig_addrs = defaultdict(dict)  # page -> {signal: {addr,...}}
        for e in entries:
            p = str(e["page"])
            a = norm_addr(e["address"])
            s = str(e["signal"]).upper().strip()
            self.page_addrs[p].add(a)
            self.sig_pages[s].add(p)
            self.page_sig_addrs[p].setdefault(s, set()).add(a)
        self.n_pages = max(1, len(self.page_addrs))
        self.ptype = classify_pages(chunks_df) if chunks_df is not None else {}

    def idf(self, sig: str) -> float:
        df = len(self.sig_pages.get(sig.upper().strip(), ())) or self.n_pages
        return math.log(1 + self.n_pages / df)

    def match_signals(self, picked: list[str], topn=None) -> dict[str, dict[str, int]]:
        """선택된 신호명 → 페이지별 {매칭 signal: 최선(가장 앞선) pick 순위}.

        두 가지 왜곡을 처리:
        - 기존의 무제한 부분문자열 매칭(`ps in su or su in ps`)은 짧은 토큰이 폭발적으로
          매칭돼 밀집 페이지를 밀어올렸다 → **단어 경계 기반**으로 제한.
        - LLM은 질문 직접 신호를 **앞에** 쓰고 뒤에 범용 전제조건 신호(EMERGENCY STOP,
          MACHINE READY…)를 20~40개 덧붙인다. 그 뭉치가 합산 점수를 지배하므로
          **pick 순위를 보존**해 뒤쪽 신호의 가중을 낮출 수 있게 한다.
        """
        pats = []
        for i, ps in enumerate(picked if topn is None else picked[:topn]):
            ps = ps.strip().upper()
            if len(ps) < 3:            # 'SP', 'M' 같은 짧은 토큰은 과매칭의 주범
                continue
            pats.append((i, ps, re.compile(r"(?<![A-Z0-9])" + re.escape(ps) + r"(?![A-Z0-9])")))
        hit = defaultdict(dict)
        for p, sigmap in self.page_sig_addrs.items():
            for s in sigmap:
                for i, ps, pat in pats:
                    if pat.search(s) or s == ps:
                        if s not in hit[p] or i < hit[p][s]:
                            hit[p][s] = i
                        break
        return hit

    def score_pages(self, picked, top_k=4, beta=0.5, gamma=1.0, alpha_type=None,
                    topn=None, rank_decay=0.0):
        """IDF·순위 가중 매칭 − 길이 정규화(β) − off-type 감점(γ).

        score(p) = Σ_{s∈matched(p)} idf(s)·rw(rank_s) / (1+log|addr(p)|)^β × type_w(p)^γ
        rw(r) = 1/(1+r)^rank_decay  — rank_decay=0이면 순위 무시(기존), 클수록 앞선 pick 중시.
        """
        type_w = alpha_type or {"parts_list": 0.15, "index": 0.3, "io_table": 1.0, "circuit": 1.0}
        hit = self.match_signals(picked, topn=topn)
        scored = []
        for p, sigmap in hit.items():
            base = sum(self.idf(s) / (1 + r) ** rank_decay for s, r in sigmap.items())
            n_addr = max(1, len(self.page_addrs[p]))
            base /= (1 + math.log(n_addr)) ** beta
            w = type_w.get(self.ptype.get(p, "circuit"), 1.0)
            scored.append((base * (w ** gamma), p, len(sigmap)))
        scored.sort(key=lambda x: -x[0])
        return scored[:top_k]

    def score_pages_2hop(self, picked, top_k=4, topn=5, keep_hop1=1):
        """**2-hop 라우팅**: 이름 → 어드레스 → 그 어드레스가 실린 회로도 페이지.

        의미 있는 신호명(CYCLE START…)은 I/O LIST 페이지에만 있고, gold 어드레스는 회로도
        페이지에 실려 있다. 1-hop(이름이 있는 페이지)만 보면 영원히 I/O LIST로만 가서
        oracle(회로도 49·56·63·80)에 도달하지 못한다. 그래서
          hop1: picked 신호 → 그 신호가 가진 어드레스 (I/O LIST의 표에서)
          hop2: 그 어드레스를 담은 **다른** 페이지 = 회로도
        를 따라간다. keep_hop1: 상위 몇 개의 hop1 페이지를 결과에 함께 남길지.
        """
        hit = self.match_signals(picked, topn=topn)
        addrs, hop1 = set(), []
        for p, sigmap in hit.items():
            for s in sigmap:
                addrs |= self.page_sig_addrs[p].get(s, set())
            hop1.append((len(sigmap), p))
        hop1.sort(reverse=True)
        src = {p for _, p in hop1[:keep_hop1]}
        scored = []
        for p, pa in self.page_addrs.items():
            if p in src:
                continue
            common = pa & addrs
            if not common:
                continue
            # 어드레스가 적게 실린 회로도일수록 그 어드레스에 특화된 페이지
            scored.append((len(common) / (1 + math.log(max(1, len(pa)))), p, len(common)))
        scored.sort(key=lambda x: -x[0])
        out = [(0.0, p, 0) for p in list(src)[:keep_hop1]] + scored
        return out[:top_k]
