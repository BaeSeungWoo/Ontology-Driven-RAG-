"""한국어 증상 표현 → 도면 영문 표기 매핑. **런타임 의존성 없음**(re만 쓴다).

`gen_questions.py`가 질문을 만들 때 쓰던 계통 표를 여기로 옮겼다. 러너의 어휘식 신호 선택
(`--sig-select lexical`)이 같은 표를 써야 "질문을 만든 근거"와 "질문에 답하는 근거"가
어긋나지 않는다. 두 곳에 복사해 두면 반드시 갈라진다.

계통(SUBSYS)만으로는 부족하다 — 터렛 문항 하나에 `TURRET`이 들어간 이름이 43~61개라
계통 매칭만으로는 6칸을 무작위로 채우는 것과 같다. 그래서 **동작어(ACTION)**를 둘째 축으로
둔다: "다음 번호로 안 돌아가고" → `INDEX`·`ROTAT`, "안 켜져요" → `LAMP|LIGHT`.
"""
from __future__ import annotations

import re

# (키, 한국어 계통명, 제목 키워드, 증상형 힌트, 모순형 힌트)
SUBSYS = [
    ("coolant", "절삭유", r"COOLANT|CUTTING FLUID|CHIP FLUSH|COOLJET",
     "절삭유가 나오지 않는다", "절삭유 탱크는 차 있는데 절삭유 알람이 뜬다"),
    ("lubrication", "윤활", r"\bLUB|LUBRICAT|GREASE|OIL MIST|GEAR OIL",
     "윤활 알람이 뜨며 기계가 멈춘다", "윤활유가 가득한데 윤활 알람이 뜬다"),
    ("chuck", "척/클램프", r"CHUCK|CLAMP|UNCLAMP|COLLET",
     "척이 물리지 않는다", "발판을 밟아도 척이 안 벌어진다"),
    ("door", "도어/안전커버", r"\bDOOR|SPLASH GUARD|SAFETY GUARD|SHUTTER",
     "자동문이 열리지 않는다", "문은 닫혔는데 도어 인터록 알람이 뜬다"),
    ("spindle", "주축", r"SPINDLE|MAIN MOTOR|ORIENT",
     "주축이 돌지 않는다", "주축 회전 명령을 줬는데 준비 완료 신호가 안 들어온다"),
    ("turret", "공구대/ATC", r"TURRET|TOOL CHANGE|\bATC\b|MAGAZINE|TOOL POST|\bINDEX",
     "공구대가 다음 번호로 돌지 않는다", "공구 교환 도중에 멈춰 알람이 뜬다"),
    ("hydraulic", "유압", r"\bHYD|HYDRAULIC",
     "유압이 안 잡힌다", "유압 펌프는 도는데 압력 부족 알람이 뜬다"),
    ("air", "공압", r"\bAIR\b|PNEUMATIC|AIR PRESSURE|AIR BLOW",
     "에어 관련 동작이 안 된다", "에어 압력은 정상인데 에어 부족 알람이 뜬다"),
    ("chip", "칩배출", r"CHIP CONVEYOR|CONVEYOR|SWARF",
     "칩컨베이어가 멈췄다", "칩컨베이어 모터는 도는데 과부하 알람이 뜬다"),
    ("light", "작업등/경광등", r"WORK LIGHT|WORKING LIGHT|PATROL|SIGNAL TOWER|\bLAMPS?\b|LIGHTING",
     "작업등이 안 켜진다", "전구를 갈았는데도 경광등이 안 켜진다"),
    ("axis", "이송축", r"AXIS|SERVO|AMPLIFIER|\bFEED\b|BRAKE",
     "축이 움직이지 않는다", "수동으로는 움직이는데 자동에서 축이 안 나간다"),
    ("emg", "비상정지/안전", r"EMG|EMERGENCY|SAFETY RELAY|INTERLOCK",
     "비상정지를 풀어도 리셋이 안 된다", "비상정지 버튼을 다 뽑았는데 알람이 안 풀린다"),
    ("tailstock", "심압대", r"TAILSTOCK|QUILL|\bCENTER\b",
     "심압대가 전진하지 않는다", "심압대는 나갔는데 확인 신호가 안 들어온다"),
    ("power", "전원", r"POWER SUPPLY|TRANSFORMER|BREAKER|MAGNETIC|CONTROL POWER|MAIN POWER",
     "제어 전원이 안 들어온다", "차단기는 올라가 있는데 제어 전원이 안 들어온다"),
    ("qsetter", "공구 측정", r"Q-SETTER|TOOL SETTER|MEASURE|PROBE|TOUCH",
     "공구 측정 장치가 반응하지 않는다", "측정기는 내려오는데 접촉 신호가 안 들어온다"),
    ("barfeeder", "바피더", r"BAR FEED|BAR PUSH|LOADER|WORK FEED",
     "바피더가 소재를 밀어주지 않는다", "소재는 남았는데 소재 없음 알람이 뜬다"),
]

# 계통을 고르는 한국어 단서. 위 표의 "계통명"만으로는 안 걸린다
# ("공구대(터렛)"에는 `공구대/ATC`라는 문자열이 없다).
SUBSYS_KO = {
    "coolant": ("절삭유", "쿨런트", "절삭액"),
    "lubrication": ("윤활", "루브", "구리스", "그리스"),
    "chuck": ("척", "클램프", "물림", "콜렛"),
    "door": ("도어", "자동문", "문", "커버", "셔터"),
    "spindle": ("주축", "스핀들"),
    "turret": ("공구대", "터렛", "타렛", "툴", "공구 교환", "공구교환", "매거진", "인덱스"),
    "hydraulic": ("유압",),
    "air": ("에어", "공압", "공기"),
    "chip": ("칩컨베이어", "칩 컨베이어", "칩배출", "컨베이어", "칩"),
    "light": ("작업등", "경광등", "패트롤", "램프", "전구", "조명"),
    "axis": ("축", "이송", "서보", "핸들", "조그"),
    "emg": ("비상정지", "비상 정지", "이머전시", "인터록", "안전"),
    "tailstock": ("심압대", "센터", "퀼"),
    "power": ("전원", "차단기", "전압", "파워"),
    "qsetter": ("공구 측정", "측정", "터치", "프로브"),
    "barfeeder": ("바피더", "바 피더", "소재", "로더"),
}

# 둘째 축 — 증상이 가리키는 **동작**. 계통 안에서 순위를 가르는 데 쓴다.
ACTION = [
    (("안 돌", "안돌", "회전", "돌지", "돌아가"), r"ROTAT|TURN|REVOLU|RUN"),
    (("번호", "인덱스", "교환", "다음"), r"INDEX|DECODE|POSITION|NO\.|CHANGE|SELECT"),
    (("멈", "정지", "스톱"), r"STOP|HALT|BRAKE"),
    (("안 켜", "안켜", "점등", "불이", "전구"), r"LAMP|LIGHT|LED|SIGNAL"),
    (("열리", "열림", "안 열"), r"OPEN"),
    (("닫히", "닫힘", "잠기"), r"CLOS|LOCK"),
    (("압력", "압이"), r"PRESSURE|PRS"),
    (("알람", "경보", "에러", "이상"), r"ALARM|OVERLOAD|TRIP|FAULT|ERROR|ABNORMAL"),
    (("과부하",), r"OVERLOAD"),
    (("확인", "신호", "안 들어", "감지"), r"CHECK|CONFIRM|DETECT|SENSOR|SWITCH"),
    (("시작", "기동", "눌러", "버튼"), r"START|BUTTON|SWITCH|\bON\b"),
    (("준비", "레디"), r"READY"),
    (("모터", "펌프"), r"MOTOR|PUMP"),
    (("밸브", "솔레노이드"), r"VALVE|\bSOL\b|SV"),
    (("발판", "풋", "페달"), r"FOOT|PEDAL|FST"),
    (("자동",), r"AUTO"),
    (("수동", "핸들", "조그", "메뉴얼"), r"MANUAL|HANDLE|MPG|JOG"),
    (("벌어", "풀리", "언클램프"), r"UNCLAMP|RELEASE|OPEN"),
    (("가득", "차 있", "레벨"), r"LEVEL|FULL|EMPTY"),
    (("안 움직", "안움직", "움직이지", "안 나가", "이동", "전진", "후진"),
     r"MOVE|TRAVEL|\bFEED\b|ADVANCE|RETURN|AXIS"),
]

_SUB_RX = {k: re.compile(rx, re.I) for k, _, rx, _, _ in SUBSYS}
_ACT = [(kos, re.compile(rx, re.I)) for kos, rx in ACTION]


def question_axes(question):
    """질문 → (계통 정규식 목록, 동작 정규식 목록). 둘 다 비면 어휘 선택을 포기해야 한다."""
    subs = [_SUB_RX[k] for k, kos in SUBSYS_KO.items() if any(t in question for t in kos)]
    acts = [rx for kos, rx in _ACT if any(t in question for t in kos)]
    return subs, acts
