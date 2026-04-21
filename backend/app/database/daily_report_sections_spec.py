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
