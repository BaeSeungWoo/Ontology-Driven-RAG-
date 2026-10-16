"""회로도/표 판독 공용 모듈 — **후보 라벨(1·2·3순위)** 방식.

라벨은 결국 OCR이라 한 개로 확정하면 오귀속이 생긴다(v4에서 `X33.6`을 "발판 신호"로 잘못
설명한 사례). VLM에게 각 어드레스마다 **가능한 라벨 후보를 확신도 순으로 최대 3개** 내게 하면
① 오귀속이 줄고 ② 이름 매칭 기회가 늘어난다.

또한 표(I/O MAP)는 **가로 전체 폭 밴드**로 잘라야 행 정렬이 유지된다 — 세로로 자르면
행 헤더(X10)와 비트열이 분리돼 `X10.5`를 엉뚱한 이름에 붙인다(공압 문항 실패 원인).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from PIL import Image

ADDR_RE = re.compile(r"[XYRGF]\d{1,3}\.\d")

# 어드레스 문법은 벤더마다 다르다 — 프롬프트가 그걸 말해 줘야 한다.
#   두산/FANUC  X10.5      (문자+숫자+점+한자리)
#   MAZAK       X080·X08A  (16진 비트, **점 없음**)
#   DECKEL MAHO I 05·Q 12  (Siemens I/Q, 점 없음)
# 기본값은 아래 ADDR_GRAMMAR — 렌더 결과가 예전 READ_SYS 문자열과 한 글자도 다르지 않다
# (scripts/regress_puma.py 가 sha로 고정한다).
ADDR_GRAMMAR = "a letter (X, Y, R, G) + digits + dot + one digit"

READ_SYS_TMPL = (
    "You read a cropped region of an electrical drawing. Find every PLC I/O address printed "
    "in it. A PLC address is {grammar}. For each "
    "address, give the possible signal names / device tags printed next to it, ordered by "
    "confidence (best first, at most 3). Output ONLY a JSON array of objects with keys "
    '"address" and "labels" (a list of strings). Copy text exactly as printed. Do not invent '
    "and do not enumerate address ranges. Output [] if the crop has no address.")
READ_SYS = READ_SYS_TMPL.format(grammar=ADDR_GRAMMAR)

# PUMA의 8칸 I/O MAP은 **두산 관례**지 업계 표준이 아니다 (results/multi/_pilot.md).
# 5종 중 3종(SMEC PL25 · MAZAK INTEGREX · DECKEL MAHO DMU125P)은 비트 행렬 표가 아니라
# **결선도**로 I/O를 문서화한다 — 한 줄에 어드레스 하나, 기능문은 그 줄의 맨 오른쪽.
#     PL25      X02.0 ─RV─ CB104(A10) ─ CM1(A10) ─ TM1(17) ─ X020 ─ READY
#     INTEGREX  X080 (HD1SEL) ──────────────────────────────→ MAIN SPINDLE SELECT
#     DMU125P   I 05 … 하단 범례표: I 10 → 3F1 pressure monitoring hydraulics
# 이 형식에 TABLE_SYS("EXACTLY 8 cells, leftmost is bit 7")를 쓰면 모델이 비트를 지어낸다.
#
# ⚠ 시트 상호참조를 **명시적으로 물어봐야** 한다. 안 물어보면 모델은 안 준다 — 결선도 4종에서
#   시트참조가 전부 0이 나와 가중치 3.0짜리 라우팅 트랙이 통째로 죽어 있었다(도면에는
#   인쇄돼 있다: PL25 `<03-15>` · VC630 `07021/2` · DMG `/043.8A` · MAZAK `018310`).
#   ROW_SYS_MERGED가 8칸 표에서 같은 교훈을 이미 겪었다(P101: "프롬프트가 crop을 따라가야 한다").
LIST_SYS_TMPL = (
    "You read one horizontal band of an electrical drawing sheet that documents PLC I/O "
    "connections. This is NOT a bit-matrix table: each PLC address sits on its OWN horizontal "
    "line, printed at the left or inside a small box, and the signal's function text is usually "
    "printed at the far RIGHT end of that same line. Between them there may be a short mnemonic, "
    "connector names and terminal numbers. A PLC address is {grammar}. "
    "For each address you can read, output one object with keys "
    '"address" and "labels" — a list containing, in this order and only if actually printed: '
    "the short mnemonic, the function text, the device tag, "
    "and the SHEET CROSS-REFERENCE printed on that line{refs}. "
    "Output ONLY a JSON array. Copy exactly what is printed; take the function text from the "
    "SAME horizontal line as the address; do not invent and do not enumerate address ranges. "
    "Output [] if this band has no address.")
LIST_SYS = LIST_SYS_TMPL.format(grammar=ADDR_GRAMMAR, refs="")
LIST_USER = "이 밴드에서 각 어드레스와 **같은 줄 오른쪽**의 기능문을 JSON 배열로 출력하세요."

# ── 세로 컬럼 결선도 (SL2500 · VC630) ─────────────────────
# 한 신호 = 세로 배선 하나. 어드레스는 **상단 띠**, 기능문은 **그 배선의 맨 아래**에 있고
# 중간에는 릴레이 품종명(`AUX RELAY`)이나 커넥터가 온다. 가로줄 프롬프트로 읽으면 중간의
# 품종명이 이름으로 굳는다(실측: SL2500 신호 40개가 전부 `AUX RELAY`).
# 두 장(같은 컬럼의 위/아래)을 함께 준다.
COLUMN_SYS_TMPL = (
    "You read ONE VERTICAL COLUMN of an electrical wiring diagram, given as TWO images: "
    "the FIRST image is the TOP of that column, the SECOND is the BOTTOM of the SAME column. "
    "Each signal is one vertical wire: its PLC address is printed in the TOP image (in a small "
    "box or strip), and the signal's FUNCTION TEXT is printed in the BOTTOM image, at the "
    "bottom end of that same wire. In between there may be a relay part name (like "
    "'AUX RELAY'), a device tag (like -KA060) and terminal numbers — those are NOT the "
    "function text. A PLC address is {grammar}. "
    "For each address you can read in the TOP image, output one object with keys "
    '"address" and "labels" — a list containing, in this order and only if actually printed: '
    "the FUNCTION TEXT from the bottom image, the device tag, the relay part name"
    "{refs}. Put the function text FIRST. "
    "Output ONLY a JSON array. Copy exactly what is printed; do not invent; "
    "if you cannot find a function text for an address, omit it rather than guessing. "
    "Output [] if the top image has no address.")
COLUMN_SYS = COLUMN_SYS_TMPL.format(grammar=ADDR_GRAMMAR, refs="")
COLUMN_USER = ("첫 이미지 상단의 각 어드레스에 대해, **두 번째 이미지 아래쪽**에 있는 "
               "그 배선의 기능문을 찾아 맨 앞에 놓고 JSON 배열로 출력하세요.")

TABLE_SYS = (
    "You read one horizontal band of an I/O MAP table from an electrical drawing. Each row "
    "has a row header (like X10 or Y4) and bit columns 7..0, so row X10 bit 5 means X10.5; "
    "each cell holds the signal name for that bit. Report every (address, signal name) pair "
    "in this band, keeping row/bit alignment exact. For each address give up to 3 candidate "
    'names ordered by confidence. Output ONLY a JSON array of objects with keys "address" '
    'and "labels" (list of strings). Copy exactly as printed; do not invent rows.')


# 부품 태그 표기도 벤더마다 다르다. 예시를 그대로 프롬프트에 박아 두면 **누출**된다 —
# DMG 도면에서 `-KM41`을 뱉게 만든다. 그래서 접두어와 예시를 인자로 뺀다.
#   두산      -KM41 (하이픈)      MAZAK  KA888·XT2 (하이픈 없음)
#   SMEC      HL14·TM1            DMG    4A1·11S1·3Q1 (IEC 81346)
DEVICE_PREFIX = "starts with a hyphen and "
DEVICE_EXAMPLES = "-KM41, -SP71, -SX31, -YV11, -KA26, -QF25, -SL5"

DEVICE_SYS_TMPL = (
    "You read a cropped region of an electrical circuit diagram. List the DEVICE TAGS printed "
    "next to component symbols. A device tag {prefix}looks like {examples}. For each tag, copy "
    "the nearby function text if any "
    '(e.g. COOLANT PUMP, TURRET UNCLAMP). Output ONLY a JSON array of objects with keys '
    '"device" and "near". Copy exactly what is printed; do not invent tags. Empty array if none.')
DEVICE_SYS = DEVICE_SYS_TMPL.format(prefix=DEVICE_PREFIX, examples=DEVICE_EXAMPLES)
DEVICE_USER = "이 영역에 그려진 부품 태그(-KM41 형식)와 옆 기능 텍스트를 JSON 배열로."
DEV_RE = re.compile(r"-([A-Z]{1,3}\d{1,3}[A-Z]?)\b")


def read_devices(llm, img_path, tmp, page, grid=(2, 2), max_new_tokens=700,
                 sys_prompt=None, dev_re=None):
    """회로도에서 **부품 태그**를 별도 패스로 수집.

    어드레스 중심 판독(READ_SYS)은 `-KM41` 같은 태그를 놓친다 — 태그는 PLC 어드레스가 아니라
    **부품 심볼 옆**에 그려지기 때문. gold가 인용하는 부품(-SP41·-SX31·-SP71 등)은 PARTS
    LIST에 없고 회로 도면에만 있으므로(측정: PARTS LIST 텍스트 10/34 vs 도면 24/34) 이 패스가
    물리 점검 서술의 재료가 된다.

    ⚠️ **`sys_prompt`와 `dev_re`를 벤더 것으로 넘겨야 한다.** 둘 다 하드코딩돼 있었고 러너가
    넘기지 않아, DMG 도면을 PUMA 예시(`-KM41`·`-SP71`)로 읽고 게다가 `DEV_RE`
    (`-[A-Z]{1,3}\d{1,3}[A-Z]?`)가 `-B2-31Q61`을 **읽어도 버렸다**. 그 결과 DMU85는
    문항당 태그 1~2개(`-X3`·`-A0`)에 그쳤고 키워드 커버리지가 13%에 묶였다 — 같은 쪽을
    벤더 프롬프트로 직접 읽으면 `-B2-31Q61`·`-B2-31Q21`·`-B2-23K11`이 기능문과 함께 나온다.
    """
    im = Image.open(img_path)
    W, H = im.size
    R, C = grid
    tmp = Path(tmp); tmp.mkdir(parents=True, exist_ok=True)
    out = {}
    for r in range(R):
        for c in range(C):
            cp = tmp / f"dev_p{int(page):04d}_{r}{c}.png"
            box = (int(W * c / C), int(H * r / R), int(W * (c + 1) / C), int(H * (r + 1) / R))
            im.crop(box).save(cp)
            zone = f"r{r}c{c}"
            try:
                raw = llm.chat_vision(sys_prompt or DEVICE_SYS, DEVICE_USER, [str(cp)],
                                      max_new_tokens=max_new_tokens, temperature=0.0)
            except Exception:
                continue
            for m in re.finditer(r'\{[^{}]*"device"\s*:\s*"([^"]+)"[^{}]*\}', raw, re.DOTALL):
                tag = m.group(1).strip().upper().replace(" ", "")
                if not tag.startswith("-"):
                    tag = "-" + tag
                if not (dev_re or DEV_RE).fullmatch(tag):
                    continue
                near = re.search(r'"near"\s*:\s*"([^"]*)"', m.group(0))
                nv = near.group(1).strip() if near else ""
                if tag not in out or len(nv) > len(out[tag]["near"]):
                    out[tag] = {"near": nv, "zone": zone, "box": list(box)}
    return [{"device": k, "near": v["near"], "page": str(page),
             "zone": v["zone"], "box": v["box"]} for k, v in out.items()]


_PROV_CHECKED = set()
_DOC_CACHE = {}


def _doc(pdf):
    """PdfDocument 핸들 재사용. 240MB 파일을 페이지마다 다시 여는 건 낭비다."""
    k = str(pdf)
    if k not in _DOC_CACHE:
        import pypdfium2 as pdfium
        _DOC_CACHE[k] = pdfium.PdfDocument(pdf)
    return _DOC_CACHE[k]


def render_page(pdf, page, out_dir, scale=4.0, doc_key=None):
    """판독용 고해상도 렌더 (200DPI로는 어드레스가 안 읽힌다). 캐시.

    ⚠ 캐시 키가 **페이지 번호뿐**이라, 다른 문서를 기본 `cache_puma/pages_400`에 겨누면
    PUMA의 픽셀을 그대로 돌려준다 — 예외도 경고도 없이 "다른 도면을 읽은 인덱스"가 나온다.
    두 겹으로 막는다:

      ① 항상: 캐시된 PNG의 치수를 이 PDF·이 scale의 기대 치수와 대조한다. 싸고, PUMA는
         이미 통과한다(3310×2336).
      ② `doc_key`가 주어지면: 디렉터리의 `provenance.json` 지문과 대조한다. VC630·DMU125P·
         DNT2600은 셋 다 842×595pt라 **치수만으로는 구분되지 않기 때문에** 이 겹이 필요하다.

    `doc_key=None`(기존 호출자 전부)이면 ②는 건너뛰므로 PUMA 경로는 그대로다.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"page_{int(page):04d}.png"

    # 출처 검사는 **doc_key 를 안 줘도** 돈다. 호출자가 --pdf 를 깜빡하면 기본 glob 이
    # PUMA를 집어 오는데, 그때 렌더 디렉터리는 다른 문서 것이다. 실측으로 PL25 디렉터리에
    # PUMA 4쪽(3310×2336)이 새로 렌더돼 들어갔다 — 캐시 히트가 아니라 **신규 렌더**라
    # 치수 대조가 발동하지 않았다. 디렉터리에 기록된 PDF와 지금 PDF가 다르면 즉시 멈춘다.
    if str(out_dir) not in _PROV_CHECKED:
        from provenance import read_provenance, check_provenance
        prov = read_provenance(out_dir)
        if prov.get("pdf") and Path(prov["pdf"]).name != Path(pdf).name:
            raise RuntimeError(
                f"렌더 디렉터리 {out_dir} 는 '{Path(prov['pdf']).name}' 의 것인데 "
                f"'{Path(pdf).name}' 를 렌더하려 한다. --pdf 를 빠뜨렸을 가능성이 크다.")
        if doc_key:
            check_provenance(out_dir, doc_key, scale)
        _PROV_CHECKED.add(str(out_dir))

    doc = _doc(pdf)
    w_pt, h_pt = doc[int(page) - 1].get_size()
    want = (round(w_pt * scale), round(h_pt * scale))
    if not p.exists():
        _im = doc[int(page) - 1].render(scale=scale).to_pil()
        _im.save(p)
        if doc_key:
            from provenance import write_provenance
            write_provenance(out_dir, pdf, scale, len(doc), {str(int(page)): list(_im.size)})
    else:
        got = Image.open(p).size
        if max(abs(want[0] - got[0]), abs(want[1] - got[1])) > 2:
            raise RuntimeError(
                f"렌더 캐시가 이 문서의 것이 아니다: {p} 는 {got}, {Path(pdf).name} p{page} "
                f"@scale{scale} 는 {want} 여야 한다. --render-dir 를 문서별로 나눠라.")
    return p


def _parse(raw, page, addr_re=None, max_labels=3):
    """{"address":..., "labels":[...]} 파싱. 실패 시 어드레스만이라도 건진다."""
    ar = addr_re or ADDR_RE
    out, seen = [], set()
    for m in re.finditer(r'\{[^{}]*"address"\s*:\s*"([^"]+)"[^{}]*\}', raw, re.DOTALL):
        a = m.group(1).strip().upper()
        if not ar.fullmatch(a):
            continue
        labs = re.findall(r'"([^"]+)"', m.group(0).split('"labels"', 1)[-1]) if '"labels"' in m.group(0) else []
        labs = [x.strip() for x in labs if x.strip() and not ar.fullmatch(x.strip())][:max_labels]
        if not labs:
            lb = re.search(r'"label"\s*:\s*"([^"]*)"', m.group(0))
            labs = [lb.group(1)] if lb and lb.group(1).strip() else []
        out.append({"address": a, "labels": labs, "page": str(page)})
        seen.add(a)
    for a in set(ar.findall(raw)) - seen:
        out.append({"address": a, "labels": [], "page": str(page)})
    return out


def _unrotate_box(box, orig_size, rotate):
    """회전 이미지의 box → **원본 좌표계**. 추적 뷰어·검증기가 같은 조각을 다시 자를 수 있어야 한다."""
    if not rotate:
        return list(box)
    x0, y0, x1, y1 = box
    W, H = orig_size                      # 원본(회전 전) 크기
    if rotate == 90:                      # PIL ROTATE_90 = 반시계 90도
        return [y0, W - x1, y1, W - x0]
    if rotate == 270:                     # 시계 90도
        return [H - y1, x0, H - y0, x1]
    return [W - x1, H - y1, W - x0, H - y0]      # 180


def read_crops(llm, img_path, tmp, page, grid=(2, 2), bands=0, sys_prompt=None,
               max_new_tokens=1200, addr_re=None, user_prompt=None, max_labels=3,
               pad_frac=None, rotate=0, band_axis="h"):
    """grid=(R,C) 격자 또는 bands=N 가로 밴드로 잘라 판독.

    표(I/O MAP)는 bands 사용 — 행 정렬 보존. 회로도는 격자 2x2가 최적(3x3은 과분할).

    `rotate`: **판독 축 교정**. 결선도는 한 신호가 세로 배선 하나라 어드레스가 상단 띠에,
    기능문이 **그 배선의 맨 아래**에 인쇄된다(SL2500 p55·VC630 p66 실측). 가로 밴드로
    자르면 두 정보가 다른 밴드로 갈라져 이름이 `AUX RELAY` 같은 품종명으로 굳는다
    (실측: SL2500 신호 40개가 전부 그랬다). 페이지를 90도 돌리면 세로 컬럼이 **가로 행**이
    되어 한 조각에서 어드레스와 기능문을 같이 읽는다. 축 판정은 VLM 한 콜로 된다
    (`{"axis":"ROW"|"COLUMN"}` — SL2500 4쪽 전부 COLUMN, PUMA는 ROW로 정확히 갈렸다).

    ⚠ `box`는 **회전 전 원본 좌표계로 되돌려** 기록한다. 안 그러면 추적 뷰어가 엉뚱한
    조각을 보여 준다 — 검증 도구가 조용히 거짓말하는 것이 가장 나쁜 실패다.
    """
    im0 = Image.open(img_path)
    if rotate:
        im = im0.transpose({90: Image.ROTATE_90, 180: Image.ROTATE_180,
                            270: Image.ROTATE_270}[rotate])
    else:
        im = im0
    W, H = im.size
    regions = []
    if bands and band_axis == "v":
        # **세로 슬라이스** — 결선도(COLUMN 축) 전용. 한 신호가 세로 배선 하나라
        # 어드레스(상단)와 기능문(하단)이 같은 x 열에 있다. 세로로 자르면 둘이 한 조각에
        # 들어온다. ⚠ 페이지를 90도 **돌리는** 방법은 실패했다 — 컬럼은 행이 되지만
        # **글자도 같이 누워** VLM이 못 읽는다(실측: SL2500 p55 40개 → 0개).
        for i in range(bands):
            x0 = int(W * i / bands); x1 = int(W * (i + 1) / bands)
            # ⚠ 기본식이 `W*0.02/bands` 였다 — 슬라이스 폭의 2%가 아니라 **페이지 폭의
            #   2%를 슬라이스 수로 또 나눈** 값이라 W=2382·9슬라이스에서 5px, 즉 사실상
            #   겹치지 않는다(가로 갈래에는 같은 실수를 이미 주석으로 적어 두고 세로 갈래만
            #   고치지 않았다). 그 결과 경계에 걸린 신호명이 **잘린 채** 인덱스에 들어갔다
            #   — DMU85 실측: `ISX_OM_1_SEL`→`ISX_OM_1_S`, `IX_GEN_BUTTON_TL_CLMP_N`→
            #   `IX_GEN_BUTTON_TL_CL`. 겹침 25%를 기본으로 주면 경계에 걸린 이름이
            #   이웃 슬라이스에 통째로 한 번 더 나온다(p52 온전한 이름 9→15개).
            pad = int(W / bands * (pad_frac if pad_frac else 0.25))
            regions.append((f"v{i}", (max(0, x0 - pad), 0, min(W, x1 + pad), H)))
    elif bands:
        for i in range(bands):
            y0 = int(H * i / bands); y1 = int(H * (i + 1) / bands)
            # 경계 행 손실 방지. 기본식 `H*0.02/bands`는 밴드 높이의 **2% 미만**이라
            # 사실상 무의미하다(H=2382·8밴드 → 5px). DECKEL MAHO에서 하단 범례 스트립이
            # 밴드 경계에 걸려 Qwen이 8밴드 전부 `[]`를 냈다(Gemma는 잘린 글자를 추측해
            # `selection of`·`switch-over` 같은 토막 라벨을 만들었다 — 더 나쁘다).
            # pad_frac 을 주면 **밴드 높이 비율**로 겹친다.
            pad = (int(H / bands * pad_frac) if pad_frac
                   else (int(H * 0.02 / bands) if bands > 1 else 0))
            regions.append((f"b{i}", (0, max(0, y0 - pad), W, min(H, y1 + pad))))
    else:
        R, C = grid
        for r in range(R):
            for c in range(C):
                regions.append((f"r{r}c{c}", (int(W * c / C), int(H * r / R),
                                              int(W * (c + 1) / C), int(H * (r + 1) / R))))
    tmp = Path(tmp)
    tmp.mkdir(parents=True, exist_ok=True)
    out = []
    for zone, box in regions:
        cp = tmp / f"p{int(page):04d}_{zone}.png"
        sub = im.crop(box)
        sub.save(cp)
        imgs = [str(cp)]
        if band_axis == "v" and sub.size[1] > sub.size[0] * 2.5:
            # 세로 슬라이스는 1:5 넘는 극단 비율이라 축소하면 하단 기능문이 뭉개진다
            # (실측: 통짜로 보내면 이름이 `AUX RELAY` 그대로였다). **상단·하단 두 장으로
            # 나눠 같이** 보내면 둘 다 읽을 만한 크기로 남고, 같은 배선의 위/아래임을
            # 프롬프트가 알려 준다.
            w, h = sub.size
            a = tmp / f"p{int(page):04d}_{zone}_t.png"
            b = tmp / f"p{int(page):04d}_{zone}_b.png"
            sub.crop((0, 0, w, int(h * 0.55))).save(a)
            sub.crop((0, int(h * 0.45), w, h)).save(b)
            imgs = [str(a), str(b)]
        try:
            raw = llm.chat_vision(sys_prompt or READ_SYS,
                                  user_prompt or "이 영역의 PLC 어드레스와 라벨 후보를 JSON 배열로.",
                                  imgs, max_new_tokens=max_new_tokens, temperature=0.0)
        except Exception:
            continue
        for e in _parse(raw, page, addr_re, max_labels):
            e["zone"] = zone
            e["box"] = _unrotate_box(box, im0.size, rotate)
            if rotate:
                e["rot"] = rotate
            out.append(e)
    return out


def merge_by_address(entries):
    """같은 어드레스의 후보 라벨을 순위 유지하며 합친다(중복 제거).

    **출처 crop(zone·box)은 버리지 않는다** — 한 어드레스가 여러 crop에서 읽힐 수 있으므로
    목록으로 모아 둔다. 이것이 없으면 "이 값이 도면 어디서 나왔나"를 사후에 복원할 수 없다
    (`scripts/build_trace_html.py`가 이 필드로 crop을 다시 잘라 보여 준다)."""
    best = {}
    for e in entries:
        k = (e["page"], e["address"])
        cur = best.setdefault(k, {"address": e["address"], "page": e["page"], "labels": [],
                                  "src": e.get("src", "DWG"),
                                  "page_prior": e.get("page_prior", 0.0),
                                  "from": []})
        for l in e["labels"]:
            if l not in cur["labels"]:
                cur["labels"].append(l)
        cur["labels"] = cur["labels"][:3]
        if e.get("zone"):
            prov = {"zone": e["zone"], "box": e.get("box")}
            if prov not in cur["from"]:
                cur["from"].append(prov)
    return list(best.values())
