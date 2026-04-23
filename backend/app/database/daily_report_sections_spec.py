# -*- coding: utf-8 -*-
"""
데일리 리포트 sections 명세 파일.

- DAILY_REPORT_SECTION_TEMPLATE:
  sections 응답의 기본 스키마(빈 구조 보장)
- DAILY_REPORT_SECTION_KEY_MAP:
  (DOMAIN_CD, STEP_NO) -> (domain_key, section_key) 매핑
"""

# 데일리 리포트 섹션의 기본 스키마.
# - 데이터가 없는 섹션도 빈 배열([])로 항상 반환되도록 키를 고정한다.
# - 프론트/다른 백엔드에서 키 존재 여부를 따로 검사하지 않고 바로 사용할 수 있다.
# -----------------------------------------------------------------------------
# [Overview]
# 이 파일은 daily report 데이터를 아래 3단계로 관리한다.
# 1) DAILY_REPORT_SECTION_TEMPLATE
#    - 도메인/섹션 구조(prod.summary 등)의 "기본 골격"
# 2) DAILY_REPORT_SECTION_KEY_MAP
#    - (DOMAIN_CD, STEP_NO) -> (domain, section) 라우팅 규칙
# 3) DAILY_REPORT_COLUMN_PROJECT_SPECS
#    - 각 최하위 섹션의 컬럼을 한글/원본키 -> 영문키로 변환하는 명세
# -----------------------------------------------------------------------------
DAILY_REPORT_SECTION_TEMPLATE = {
    # 생산
    "prod": {
        "summary": [],                      # 생산요약
        "underperform": [],                 # 실적미달
        "processBottleneck": [],            # 공정병목
        "equipmentBottleneck": [],          # 설비병목
        "equipmentResult": [],              # 설비실적
        "workerEfficiency": [],             # 작업자효율
        "equipmentUtilization": [],         # 설비가동
    },
    # 출하
    "ship": {
        "summary": [],                      # 출하요약
        "customerShipment": [],             # 고객별출하
        "shipmentStatus": [],               # 출하상태
        "delayCause": [],                   # 지연원인분석
    },
    # 납기
    "delv": {
        "summary": [],                      # 납기요약
        "riskAnalysis": [],                 # 납기위험분석
        "impactAnalysis": [],               # 납기영향분석
        "riskCurrent": [],                  # 납기리스크분석
        "actions": [],                      # 조치사항
        "issues": [],                       # 납기이슈
    },
    # 품질
    "qual": {
        "summary": [],                      # 품질요약
        "processQuality": [],               # 공정별품질
        "defectComposition": [],            # 불량구성
        "equipmentQuality": [],             # 설비별품질
        "workerQuality": [],                # 작업자품질
        "qualityIssues": [],                # 품질리스크
        "customerImpact": [],               # 고객영향
    },
    # 설비
    "equip": {
        "statusSummary": [],                # 설비요약
        "alarmAnalysis": [],                # 알람분석
        "downtimeImpact": [],               # 설비영향
    },
    # 근태
    "att": {
        "summary": [],                      # 근태요약
        "absenceImpact": [],                # 결근영향
        "overtimeStatus": [],               # 잔업현황
    },
}

# 프로시저 결과셋을 비즈니스 섹션으로 연결하는 매핑 테이블.
# - 기준: (DOMAIN_CD, STEP_NO)
# - 값: (도메인 키, 섹션 키)
# 예) ("PROD", 3) => sections["prod"]["processBottleneck"]
# [Step 2] DB 식별값을 domain.section으로 연결
# 예: ("PROD", 3) -> ("prod", "processBottleneck")
DAILY_REPORT_SECTION_KEY_MAP = {
    ("PROD", 1): ("prod", "summary"),
    ("PROD", 2): ("prod", "underperform"),
    ("PROD", 3): ("prod", "processBottleneck"),
    ("PROD", 4): ("prod", "equipmentBottleneck"),
    ("PROD", 5): ("prod", "equipmentResult"),
    ("PROD", 6): ("prod", "workerEfficiency"),
    ("PROD", 7): ("prod", "equipmentUtilization"),
    ("SHIP", 1): ("ship", "summary"),
    ("SHIP", 2): ("ship", "customerShipment"),
    ("SHIP", 3): ("ship", "shipmentStatus"),
    ("SHIP", 4): ("ship", "delayCause"),
    ("DELV", 1): ("delv", "summary"),
    ("DELV", 2): ("delv", "riskAnalysis"),
    ("DELV", 3): ("delv", "impactAnalysis"),
    ("DELV", 4): ("delv", "riskCurrent"),
    ("DELV", 5): ("delv", "actions"),
    ("DELV", 6): ("delv", "issues"),
    ("QUAL", 1): ("qual", "summary"),
    ("QUAL", 2): ("qual", "processQuality"),
    ("QUAL", 3): ("qual", "defectComposition"),
    ("QUAL", 4): ("qual", "equipmentQuality"),
    ("QUAL", 5): ("qual", "workerQuality"),
    ("QUAL", 6): ("qual", "qualityIssues"),
    ("QUAL", 7): ("qual", "customerImpact"),
    ("EQUIP", 1): ("equip", "statusSummary"),
    ("EQUIP", 2): ("equip", "alarmAnalysis"),
    ("EQUIP", 3): ("equip", "downtimeImpact"),
    ("ATT", 1): ("att", "summary"),
    ("ATT", 2): ("att", "absenceImpact"),
    ("ATT", 3): ("att", "overtimeStatus"),
}

# =============================================================================
# Full Section Projection Registry
# - 모든 (domain, section) 키를 보유하고, 필요한 섹션만 라우터에서 선택 사용한다.
# =============================================================================

# [Step 3] 최하위 섹션 컬럼 변환 명세
# key: (domain, section)
# value: {
#   "eng_key": {"source": ("원본키1", "원본키2"), "type": "int|float|str", "default": ...}
# }
# 참고:
# - spec이 {} 인 섹션은 아직 컬럼 변환 규칙이 없는 상태다.
# - 이 경우 project helper는 원본 row를 그대로 반환한다.
DAILY_REPORT_COLUMN_PROJECT_SPECS = {
    ("prod", "summary"): {
        "planQty": {"source": ("계획수량", "planQty"), "type": "int", "default": 0},
        "qty": {"source": ("실적수량", "qty"), "type": "int", "default": 0},
        "achiveRate": {"source": ("달성률", "achiveRate", "achieveRate"), "type": "float", "default": 0.0},
        "totalEquipQty": {"source": ("총설비수", "totalEquipQty"), "type": "int", "default": 0},
        "runningEquipQty": {"source": ("가동설비수", "runningEquipQty"), "type": "int", "default": 0},
    },
    ("prod", "underperform"): {
        "orderNo": {"source": ("수주번호", "orderNo", "ordNo"), "type": "str", "default": ""},
        "seqNo": {"source": ("수주순번", "seqNo"), "type": "int", "default": 0},
        "itemCode": {"source": ("품목코드", "itemCode"), "type": "str", "default": ""},
        "processSeq": {"source": ("공정순번", "processSeq"), "type": "int", "default": 0},
        "processName": {"source": ("공정명", "processName"), "type": "str", "default": ""},
        "planQty": {"source": ("계획수량", "planQty"), "type": "int", "default": 0},
        "actualQty": {"source": ("실적수량", "actualQty", "qty"), "type": "float", "default": 0.0},
        "achiveRate": {"source": ("달성률", "achiveRate", "achieveRate"), "type": "float", "default": 0.0},
    },
    ("prod", "processBottleneck"): {
        "processCode": {"source": ("공정코드", "processCode"), "type": "str", "default": ""},
        "processName": {"source": ("공정명", "processName"), "type": "str", "default": ""},
        "requiredTime": {"source": ("요구시간", "requiredTime"), "type": "float", "default": 0.0},
        "availableTime": {"source": ("가용시간", "availableTime"), "type": "float", "default": 0.0},
        "overTime": {"source": ("초과시간", "overTime"), "type": "float", "default": 0.0},
        "utilization": {"source": ("부하율", "utilization"), "type": "float", "default": 0.0},
    },
    ("prod", "equipmentBottleneck"): {
        "equipmentCode": {"source": ("설비코드", "equipmentCode"), "type": "str", "default": ""},
        "equipmentName": {"source": ("설비명", "equipmentName"), "type": "str", "default": ""},
        "requiredTime": {"source": ("요구시간", "requiredTime"), "type": "float", "default": 0.0},
        "availableTime": {"source": ("가용시간", "availableTime"), "type": "float", "default": 0.0},
        "overTime": {"source": ("초과시간", "overTime"), "type": "float", "default": 0.0},
        "utilization": {"source": ("부하율", "utilization"), "type": "float", "default": 0.0},
    },
    ("prod", "equipmentResult"): {
        "equipmentCode": {"source": ("설비코드", "equipmentCode"), "type": "str", "default": ""},
        "equipmentName": {"source": ("설비명", "equipmentName"), "type": "str", "default": ""},
        "processCode": {"source": ("공정코드", "processCode"), "type": "str", "default": ""},
        "processName": {"source": ("공정명", "processName"), "type": "str", "default": ""},
        "timeSlot": {"source": ("시간대", "timeSlot"), "type": "int", "default": 0},
        "outputQty": {"source": ("생산량", "outputQty"), "type": "float", "default": 0.0},
    },
    ("prod", "workerEfficiency"): {
        "workerId": {"source": ("작업자ID", "workerId"), "type": "str", "default": ""},
        "workerName": {"source": ("작업자명", "workerName"), "type": "str", "default": ""},
        "processName": {"source": ("공정명", "processName"), "type": "str", "default": ""},
        "outputQty": {"source": ("생산량", "outputQty"), "type": "float", "default": 0.0},
        "workTime": {"source": ("작업시간", "workTime"), "type": "int", "default": 0},
        "standardTime": {"source": ("표준시간", "standardTime"), "type": "float", "default": 0.0},
        "efficiency": {"source": ("효율", "efficiency"), "type": "float", "default": 0.0},
        "output_per_hour": {"source": ("시간당 실적", "output_per_hour"), "type": "float", "default": 0.0},
        "standard_per_hour": {"source": ("시간당 기준", "standard_per_hour"), "type": "float", "default": 0.0},
    },
    ("prod", "equipmentUtilization"): {
        "equipmentCode": {"source": ("설비코드", "equipmentCode"), "type": "str", "default": ""},
        "equipmentName": {"source": ("설비명", "equipmentName"), "type": "str", "default": ""},
        "availableTime": {"source": ("가용시간", "availableTime"), "type": "int", "default": 0},
        "runTime": {"source": ("가동시간", "runTime"), "type": "int", "default": 0},
        "standardTime": {"source": ("표준시간", "standardTime"), "type": "float", "default": 0.0},
        "equipLoss": {"source": ("설비손실", "equipLoss"), "type": "float", "default": 0.0},
        "workLoss": {"source": ("작업손실", "workLoss"), "type": "float", "default": 0.0},
        "planLoss": {"source": ("계획손실", "planLoss"), "type": "float", "default": 0.0},
        "utilizationRate": {"source": ("가동률", "utilizationRate"), "type": "float", "default": 0.0},
        "planRate": {"source": ("계획율", "planRate"), "type": "float", "default": 0.0},
        "efficiency": {"source": ("효율", "efficiency"), "type": "float", "default": 0.0},
    },
    ("ship", "summary"): {
        "planQty": {"source": ("계획수량", "planQty"), "type": "int", "default": 0},
        "shipQty": {"source": ("출하수량", "shipQty"), "type": "int", "default": 0},
        "shipAmt": {"source": ("출하금액", "shipAmt"), "type": "int", "default": 0},
        "delayQty": {"source": ("지연수량", "delayQty"), "type": "int", "default": 0},
        "leadtimeAVG": {"source": ("평균리드타임", "leadtimeAVG"), "type": "int", "default": 0},
    },
    ("ship", "customerShipment"): {
        "customerCode": {"source": ("거래처코드", "customerCode"), "type": "str", "default": ""},
        "customerName": {"source": ("거래처명", "customerName"), "type": "str", "default": ""},
        "orderNo": {"source": ("수주번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("수주행", "orderDetailNo"), "type": "int", "default": 0},
        "orderQty": {"source": ("수주수량", "orderQty"), "type": "int", "default": 0},
        "planDate": {"source": ("계획일자", "planDate"), "type": "str", "default": ""},
        "shipQty": {"source": ("출하수량", "shipQty"), "type": "int", "default": 0},
        "shipAmt": {"source": ("출하금액", "shipAmt"), "type": "int", "default": 0},
    },
    ("ship", "shipmentStatus"): {
        "orderNo": {"source": ("수주번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("수주행", "orderDetailNo"), "type": "int", "default": 0},
        "customerName": {"source": ("고객명", "customerName"), "type": "str", "default": ""},
        "itemCode": {"source": ("품목코드", "itemCode"), "type": "str", "default": ""},
        "itemName": {"source": ("품목명", "itemName"), "type": "str", "default": ""},
        "planQty": {"source": ("계획수량", "planQty"), "type": "int", "default": 0},
        "shipQty": {"source": ("출하수량", "shipQty"), "type": "int", "default": 0},
        "remainQty": {"source": ("미출하수량", "remainQty"), "type": "int", "default": 0},
        "shipState": {"source": ("출하상태", "shipState"), "type": "str", "default": ""},
        "lateDay": {"source": ("지연일수", "lateDay"), "type": "int", "default": 0},
    },
    ("ship", "delayCause"): {
        "orderNo": {"source": ("수주번호", "orderNo"), "type": "str", "default": ""},
        "customerName": {"source": ("고객명", "customerName"), "type": "str", "default": ""},
        "itemName": {"source": ("품목명", "itemName"), "type": "str", "default": ""},
        "delayQty": {"source": ("지연수량", "delayQty"), "type": "int", "default": 0},
        "delayCause": {"source": ("지연사유", "delayCause"), "type": "str", "default": ""},
    },
    ("delv", "summary"): {
        "totalCnt": {"source": ("전체건수", "totalCnt"), "type": "int", "default": 0},
        "passCnt": {"source": ("정상건수", "passCnt"), "type": "int", "default": 0},
        "dangerCnt": {"source": ("위험건수", "dangerCnt"), "type": "int", "default": 0},
        "delayCnt": {"source": ("지연건수", "delayCnt"), "type": "int", "default": 0},
        "delvRate": {"source": ("납기율", "delvRate"), "type": "float", "default": 0.0},
    },
    ("delv", "riskAnalysis"): {
        "customerName": {"source": ("고객", "customerName"), "type": "str", "default": ""},
        "orderNo": {"source": ("주문번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("순번", "orderDetailNo"), "type": "int", "default": 0},
        "itemName": {"source": ("품목", "itemName"), "type": "str", "default": ""},
        "qty": {"source": ("수량", "qty"), "type": "int", "default": 0},
        "cause": {"source": ("사유", "cause"), "type": "str", "default": ""},
        "state": {"source": ("상태", "state"), "type": "str", "default": ""},
    },
    ("delv", "impactAnalysis"): {
        "customerName": {"source": ("고객", "customerName"), "type": "str", "default": ""},
        "orderNo": {"source": ("주문번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("순번", "orderDetailNo"), "type": "int", "default": 0},
        "itemName": {"source": ("품목", "itemName"), "type": "str", "default": ""},
        "totalQty": {"source": ("총수량", "totalQty"), "type": "int", "default": 0},
        "dangerQty": {"source": ("위험수량", "dangerQty"), "type": "int", "default": 0},
    },
    ("delv", "riskCurrent"): {
        "orderNo": {"source": ("주문번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("순번", "orderDetailNo"), "type": "int", "default": 0},
        "itemName": {"source": ("품목", "itemName"), "type": "str", "default": ""},
        "delvDate": {"source": ("납기일", "delvDate"), "type": "str", "default": ""},
        "orderQty": {"source": ("수량", "orderQty"), "type": "int", "default": 0},
        "prodQty": {"source": ("생산수량", "prodQty"), "type": "int", "default": 0},
        "process": {"source": ("공정", "process"), "type": "str", "default": ""},
        "state": {"source": ("상태", "state"), "type": "str", "default": ""},
    },
    ("delv", "actions"): {
        "orderNo": {"source": ("주문번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("순번", "orderDetailNo"), "type": "int", "default": 0},
        "itemName": {"source": ("품목", "itemName"), "type": "str", "default": ""},
        "delvDate": {"source": ("납기일", "delvDate"), "type": "str", "default": ""},
        "orderQty": {"source": ("수량", "orderQty"), "type": "int", "default": 0},
        "prodQty": {"source": ("생산수량", "prodQty"), "type": "int", "default": 0},
        "process": {"source": ("공정", "process"), "type": "str", "default": ""},
        "state": {"source": ("상태", "state"), "type": "str", "default": ""},
        "action": {"source": ("조치내용", "action"), "type": "str", "default": ""},
    },
    ("delv", "issues"): {
        "orderNo": {"source": ("주문번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("순번", "orderDetailNo"), "type": "int", "default": 0},
        "itemName": {"source": ("품목", "itemName"), "type": "str", "default": ""},
        "delayDay": {"source": ("지연일", "delayDay"), "type": "int", "default": 0},
        "requireQty": {"source": ("부족수량", "requireQty"), "type": "int", "default": 0},
        "cause": {"source": ("원인", "cause"), "type": "str", "default": ""},
        "process": {"source": ("공정", "process"), "type": "str", "default": ""},
        "rank": {"source": ("우선순위", "rank"), "type": "str", "default": ""},
        "actionDate": {"source": ("조치기한", "actionDate"), "type": "str", "default": ""},
        "part": {"source": ("담당부서", "part"), "type": "str", "default": ""},
    },
    ("qual", "summary"): {
        "totalQty": {"source": ("총검사수량", "totalQty"), "type": "int", "default": 0},
        "qty": {"source": ("양품수량", "qty"), "type": "int", "default": 0},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "defectRate": {"source": ("불량률", "defectRate"), "type": "float", "default": 0.0},
        "ppm": {"source": ("PPM", "ppm"), "type": "int", "default": 0},
    },
    ("qual", "processQuality"): {
        "defectProc": {"source": ("공정", "defectProc"), "type": "str", "default": ""},
        "equipName": {"source": ("설비", "equipName"), "type": "str", "default": ""},
        "processCode": {"source": ("공정코드", "processCode"), "type": "str", "default": ""},
        "processName": {"source": ("공정명", "processName"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "defectRate": {"source": ("불량률", "defectRate"), "type": "float", "default": 0.0},
    },
    ("qual", "defectComposition"): {
        "result": {"source": ("불량결과", "result"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "defectRatio": {"source": ("구성비", "defectRatio"), "type": "str", "default": ""},
    },
    ("qual", "equipmentQuality"): {
        "defectType": {"source": ("불량유형", "defectType"), "type": "str", "default": ""},
        "equipName": {"source": ("설비명", "equipName"), "type": "str", "default": ""},
        "cause": {"source": ("불량원인", "cause"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
    },
    ("qual", "workerQuality"): {
        "workerId": {"source": ("사번", "workerId"), "type": "str", "default": ""},
        "workerName": {"source": ("작업자명", "workerName"), "type": "str", "default": ""},
        "defectType": {"source": ("불량유형", "defectType"), "type": "str", "default": ""},
        "cause": {"source": ("불량원인", "cause"), "type": "str", "default": ""},
        "processName": {"source": ("공정", "processName"), "type": "str", "default": ""},
        "equipName": {"source": ("설비", "equipName"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "defectRate": {"source": ("불량률", "defectRate"), "type": "float", "default": 0.0},
    },
    ("qual", "qualityIssues"): {
        "orderNo": {"source": ("수주번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("행번", "orderDetailNo"), "type": "int", "default": 0},
        "itemCode": {"source": ("품목코드", "itemCode"), "type": "str", "default": ""},
        "itemName": {"source": ("품명", "itemName"), "type": "str", "default": ""},
        "customerName": {"source": ("고객", "customerName"), "type": "str", "default": ""},
        "delvDate": {"source": ("납기일", "delvDate"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "result": {"source": ("불량결과", "result"), "type": "str", "default": ""},
        "liskRate": {"source": ("리스크율", "liskRate"), "type": "float", "default": 0.0},
        "danger": {"source": ("위험여부", "danger"), "type": "str", "default": ""},
    },
    ("qual", "customerImpact"): {
        "inspNum": {"source": ("검사지시번호", "inspNum"), "type": "str", "default": ""},
        "workNum": {"source": ("작업지시번호", "workNum"), "type": "str", "default": ""},
        "orderNo": {"source": ("수주번호", "orderNo"), "type": "str", "default": ""},
        "orderDetailNo": {"source": ("행번", "orderDetailNo"), "type": "int", "default": 0},
        "itemCode": {"source": ("품목코드", "itemCode"), "type": "str", "default": ""},
        "itemName": {"source": ("품명", "itemName"), "type": "str", "default": ""},
        "defectType": {"source": ("불량분류", "defectType"), "type": "str", "default": ""},
        "cause": {"source": ("불량원인", "cause"), "type": "str", "default": ""},
        "defectQty": {"source": ("불량수량", "defectQty"), "type": "int", "default": 0},
        "customerName": {"source": ("고객명", "customerName"), "type": "str", "default": ""},
    },
    ("equip", "statusSummary"): {
        "totalEquipQty": {"source": ("전체설비수", "totalEquipQty"), "type": "int", "default": 0},
        "runningEquipQty": {"source": ("가동설비수", "runningEquipQty"), "type": "int", "default": 0},
        "runningRate": {"source": ("가동률", "runningRate"), "type": "float", "default": 0},
        "alarmEquipQty": {"source": ("알람설비수", "alarmEquipQty"), "type": "int", "default": 0},
        "alarmCnt": {"source": ("알람건수", "alarmCnt"), "type": "int", "default": 0},
        "status": {"source": ("설비상태", "status"), "type": "str", "default": "정상"},
    },
    ("equip", "alarmAnalysis"): {
        "equipCode": {"source": ("설비코드", "equipCode"), "type": "str", "default": ""},
        "equipName": {"source": ("설비명", "equipName"), "type": "str", "default": ""},
        "alramCode": {"source": ("알람코드", "alramCode"), "type": "str", "default": ""},
        "alramMessage": {"source": ("알람내용", "alramMessage"), "type": "str", "default": ""},
        "action": {"source": ("조치내용", "action"), "type": "str", "default": ""},
    },
    ("equip", "downtimeImpact"): {
        "equipCode": {"source": ("설비코드", "equipCode"), "type": "str", "default": ""},
        "equipName": {"source": ("설비명", "equipName"), "type": "str", "default": ""},
        "effect": {"source": ("영향내용", "effect"), "type": "str", "default": ""},
        "effectTime": {"source": ("영향시간", "effectTime"), "type": "str", "default": ""},
        "stopTime": {"source": ("설비정지시간", "stopTime"), "type": "str", "default": ""},
    },
    ("att", "summary"): {
        "total": {"source": ("총인원", "total"), "type": "int", "default": 0},
        "work": {"source": ("출근", "work"), "type": "int", "default": 0},
        "absence": {"source": ("결근", "absence"), "type": "int", "default": 0},
        "overtime": {"source": ("잔업", "overtime"), "type": "int", "default": 0},
    },
    ("att", "absenceImpact"): {},
    ("att", "overtimeStatus"): {},
}

_CASTERS = {
    "int": lambda value, default=0: _to_int(value, default),
    "float": lambda value, default=0.0: _to_float(value, default),
    "str": lambda value, default="": _to_str(value, default),
}


def _to_int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def _to_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _to_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def get_section_projection_spec(domain_key: str, section_key: str) -> dict:
    """
    (domain, section)에 해당하는 컬럼 변환 스펙을 반환한다.
    미정의 섹션은 빈 dict를 반환한다.
    """
    return DAILY_REPORT_COLUMN_PROJECT_SPECS.get((domain_key, section_key), {})


def project_row_by_spec(row: dict | None, spec: dict) -> dict:
    """
    단일 row를 spec에 맞춰 영문 컬럼으로 변환한다.
    """
    if not spec:
        return row if isinstance(row, dict) else {}

    if row is None:
        return {eng: field_spec.get("default") for eng, field_spec in spec.items()}

    out = {}
    for eng, field_spec in spec.items():
        source = field_spec.get("source")
        value_type = field_spec.get("type", "str")
        default = field_spec.get("default")

        if isinstance(source, (tuple, list)):
            raw = default
            for key in source:
                if key in row:
                    raw = row.get(key, default)
                    break
        else:
            raw = row.get(source, default)

        caster = _CASTERS.get(value_type, _CASTERS["str"])
        out[eng] = caster(raw, default)

    return out


def project_rows_by_spec(rows: list, spec: dict) -> list:
    """
    row list를 spec에 맞춰 변환한다.
    """
    if not isinstance(rows, list):
        return []
    return [
        project_row_by_spec(row if isinstance(row, dict) else None, spec)
        for row in rows
    ]


def project_section_rows(report: dict, domain_key: str, section_key: str) -> list:
    """
    report에서 특정 섹션 row list를 읽어 변환 스펙 적용 후 반환한다.
    """
    domain_data = report.get(domain_key, {}) if isinstance(report, dict) else {}
    rows = domain_data.get(section_key, []) if isinstance(domain_data, dict) else []
    spec = get_section_projection_spec(domain_key, section_key)
    return project_rows_by_spec(rows, spec)


def project_section_first_row(report: dict, domain_key: str, section_key: str) -> dict:
    """
    report에서 특정 섹션의 첫 번째 row를 읽어 변환 스펙 적용 후 반환한다.
    """
    rows = project_section_rows(report, domain_key, section_key)
    if not rows:
        spec = get_section_projection_spec(domain_key, section_key)
        return project_row_by_spec(None, spec)
    row = rows[0]
    return row if isinstance(row, dict) else {}
