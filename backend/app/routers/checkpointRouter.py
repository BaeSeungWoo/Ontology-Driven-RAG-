from fastapi import APIRouter, HTTPException
from datetime import date, timedelta
from pydantic import BaseModel, Field
from app.database import database
from app.database.daily_report_sections_spec import (
    project_section_first_row,
    project_section_rows,
)

checkpointRouter = APIRouter(prefix="/api/checkpoint", tags=["checkpoint"])

class ReportSectionsRequest(BaseModel):
    date: date
    reportId: str = Field(min_length=1) #현재는 "OBI" 로 들어와서 string, 추후 reportId가 number형식이면 수정 고려
    locale: str = Field(min_length=2, max_length=10)  # 예: ko_KR

# ==============================
#   공통 유틸 함수
# ==============================
def to_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default

def get_previous_report_date(target_date: date) -> date:
    """
    기준일의 직전 조회일을 반환한다.
    - 기본: 전일
    - 월요일: 직전 금요일
    """
    if target_date.weekday() == 0:  # Monday
        return target_date - timedelta(days=3)
    return target_date - timedelta(days=1)

def get_daily_report(report_date: date, report_id: str, locale: str) -> dict:
    """
    데일리 리포트 원본을 1회 조회하고, 비정상 응답이면 예외를 발생시킨다.
    """
    report = database.getDailyReport(report_date, report_id, locale)
    if not isinstance(report, dict):
        raise ValueError("daily report response is not dict")
    return report

# ==============================
#   CheckPoint Test
# ==============================
@checkpointRouter.post("/getCheckPointSections")
def getCheckPointSections(req: ReportSectionsRequest):
    """
    체크포인트 테스트.
    전체 섹션을 한 번에 반환한다.
    - DB의 getDailyReport()는 이 요청 안에서 1회만 호출한다.

    report = {
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
    """
    try:
        # 전체 데이터
        report = get_daily_report(req.date, req.reportId, req.locale)
        # 전일 데이터
        previous_report_date = get_previous_report_date(req.date)
        previous_report = get_daily_report(previous_report_date, req.reportId, req.locale)

        # 1. 경영층 요약
        section01_Data = _build_summary(report)
        # 2. 생산 현황
        section02_Data = _build_production(report, previous_report)
        # 3. 출하 현황
        section03_Data = _build_shipping(report)
        # 4. 납기 현황
        section04_Data = _build_delivery(report)
        # 5. 품질 현황
        section05_Data = _build_quality(report)
        # 6. 설비 현황
        section06_Data = _build_equip(report)

        #TODO: 각 섹션에 대한 현황을 보고 종합요약하는 DailyReport 용 데이터셋을 만들어야 함

        return {
            # "report": report,
            "Section_01": section01_Data,
            "Section_02": section02_Data,
            "Section_03": section03_Data,
            "Section_04": section04_Data,
            "Section_05": section05_Data,
            "Section_06": section06_Data,
        }
    
    except Exception as e:
        print(f"getReportSections error: {e}")
        raise HTTPException(
            status_code=500,
            detail="데일리리포트 - 통합 섹션 조회 중 오류가 발생했습니다.",
        )

# ==============================
#   01_ 경영층 요약 
# ==============================

def _build_summary(report: dict):
    """
    각 도메인의 summary[0] 한 행만 읽어 metrics로 변환한다.
    그리고 해당 metrics에 대한 코멘트와 핵심이슈를 LLM에게 얻어온다.
    """
    summary_sections = {
        "product": ("prod", "summary"),
        "shipment": ("ship", "summary"),
        "delivery": ("delv", "summary"),
        "quality": ("qual", "summary"),
        "equipment": ("equip", "statusSummary"),
        "attendance": ("att", "summary"),
    }

    report_data = report if isinstance(report, dict) else {}
    metrics = {
        metric_key: project_section_first_row(report_data, domain_key, section_key)
        for metric_key, (domain_key, section_key) in summary_sections.items()
    }

    # TODO: 전체 데이터를 LLM에게 보내 핵심 이슈와 요약내용에 대한 코멘트를 얻어오는 로직
    # result = logic(report, metrics)
    
    keyIssue = [
        "[설비] CNC-03 호기 스핀들 이상진동 알람 3회 발생 → 생산 차질 약 120분, 납기 리스크 확산",
        "[품질] 도장공정 불량률 3.1% (목표의 2배) → LOT 2건 전수검사 진행 중",
        "[납기] 거래처 A사 주문 4건 중 2건 납기 위험 단계 진입 → 생산순위 재조정 필요"
    ]

    summaryDatas = {
        "summary": metrics,
        "comment": "금일 제조 현장은 전반적으로 안정 운영 상태이나, 일부 라인에서 설비 알람 및 납기 리스크가 식별되어 조치가 필요합니다. 핵심지표 요약은 다음과 같습니다.",
        "keyIssue": keyIssue,
    }

    return summaryDatas

# ==============================
#   02_ 생산 현황 
# ==============================

def _build_production(report: dict, past_report: dict):
    """
    오늘 리포트(report)와 전일 리포트(past_report)를 받아, LLM에게 오늘/전일을 비교한
    생산요약 코멘트, 실적미달 코멘트(?), 설비 병목및 가동률에 대한 코멘트를 받는다.
    """

    #TODO: 전일,오늘 데이터를 비교하여 나온 코멘트들을 받는 로직.
    # 1. 오늘과 전일의 생산요약을 비교하여 나온 코멘트
    # 2. 실적미달에 대한 코멘트
    # 3. 설비 병목 및 가동률에 대한 코멘트
    
    # 2.1 생산요약 (영문 컬럼 변환본)
    summaryData = project_section_rows(report, "prod", "summary")
    past_summaryData = project_section_rows(past_report, "prod", "summary")
    # summaryComment = getComment(summaryData, past_summaryData)
    
    # 2.2 실적미달 LOT (영문 컬럼 변환본)
    # underperform의 데이터들 중 달성률 기준미달만 조회 예) 조건: 달성률 90% 미만 
    underperformDataAll = project_section_rows(report, "prod", "underperform")
    underperformData = [
        row for row in underperformDataAll
        if isinstance(row, dict) and to_float(row.get("achiveRate"), 100.0) < 90
    ]

    # 2.3 설비 병목 및 가동률 (영문 컬럼 변환본)
    equipmentBottleneckData = project_section_rows(report, "prod", "equipmentBottleneck")
    equipmentUtilizationData = project_section_rows(report, "prod", "equipmentUtilization")

    example = {
        "summary": summaryData,
        "summaryComment": "금일 총 계획 18,500EA 대비 실적 17,094EA를 달성하여 달성률 92.4%를 기록하였습니다. 전일 대비 2.6%p 하락했으며 주 원인은 CNC-03호기 설비 이상 및 도장공정 재작업입니다.",
        "underperform": underperformData,
        "underperformComment": "계획 달성률 90% 미만 LOT x건이 식별되었습니다.",
        "equipmentBottleneck": equipmentBottleneckData,
        "equipmentUtilization": equipmentUtilizationData,
        "equipComment": "설비 병목과 가동률에 대한 브리핑 코멘트가 들어갈 예정입니다. 이걸 하나의 텍스트로 묶을지, string[] 형식으로 할지는 미정입니다."
    }
    return example

# ==============================
#   03_ 출하 현황 
# ==============================

def _build_shipping(report: dict):
    """
    출하에 대한 요약, 상태, 지연원인을 LLM에게 전달해 답변을 받는다.
    """

    # 3.1 출하요약
    summaryData = project_section_rows(report, "ship", "summary")

    # 3.2 출하상태 / 지연현황
    shipStateData = project_section_rows(report, "ship", "shipmentStatus")

    # 3.3 지연원인 분석
    delayCauseData = project_section_rows(report, "ship", "delayCause")

    #TODO: 각 데이터에 대한 코멘트를 받는다
    # getComment = logic(summaryData, shipStateData, delayCauseData)

    example = {
        "summary": summaryData,
        "summaryComment": "출하요약에 대한 코멘트를 받습니다.",
        "shipState": shipStateData,
        "shipStateComment": "미출하 n건이 발생했으며, A고객사 주문으로, 지연일수는 이렇습니다.",
        "delayCause": delayCauseData,
        "delayCauseComment": "수주번호(품목명 지연수량 지연): 지연사유"
    }

    return example

# ==============================
#   04_ 납기 현황 
# ==============================

def _build_delivery(report: dict):
    """
    납기요약, 납기이슈
    """

    # 4.1 납기요약
    summaryData = project_section_rows(report, "delv", "summary")
    # 4.2 납기이슈
    issueData = project_section_rows(report, "delv", "issues")

    #TODO: 납기이슈 우선순위 TOP5를 지정한다.
    #

    example = {
        "summary": summaryData,
        "summaryComment": "납기요약에 대한 답변을 받습니다.",
        "issues": issueData,
        "issuesComment": "납기이슈에 대한 답변을 받습니다."
    }

    return example

# ==============================
#   05_ 품질 현황 
# ==============================

def _build_quality(report: dict):
    """
    품질요약, 공정별 품질현황, 불량구성, 품질리스크 - 고객영향
    """

    # 5.1 품질요약
    summaryData = project_section_rows(report, "qual", "summary")
    # 5.2 공정별 품질 현황
    processQualData = project_section_rows(report, "qual", "processQuality")
    # 5.3 불량구성
    defectData = project_section_rows(report, "qual", "defectComposition")
    # 5.4 품질 리스크 - 고객영향
    liskData = project_section_rows(report, "qual", "qualityIssues")
    custData = project_section_rows(report, "qual", "customerImpact")

    #TODO: 
    #

    example = {
        "summary": summaryData,
        "summaryComment": "품질요약에 대한 답변을 받습니다.",
        "processQual": processQualData,
        "processQualComment": "공정별 품질 현황에 대한 답변을 받습니다.",
        "defect": defectData,
        "defectComment": "불량구성에 대한 답변을 받습니다.",
        "lisk": liskData,
        "liskComment": "품질 리스크에 대한 답변을 받습니다.",
        "custImpact": custData,
        "custImpactComment": "고객영향에 대한 답변을 받습니다."
    }

    return example
# ==============================
#   06_ 설비 현황 
# ==============================

def _build_equip(report: dict):
    """
    설비 요약, 설비 알람분석, 설비 영향분석
    """

    # 6.1 설비 요약
    summaryData = project_section_rows(report, "equip", "statusSummary")
    # 6.2 설비 알람 분석
    alramData = project_section_rows(report, "equip", "alarmAnalysis")
    # 6.3 설비 영향 분석
    effectData = project_section_rows(report, "equip", "downtimeImpact")

    #TODO: 
    #

    example = {
        "summary": summaryData,
        "summaryComment": "설비요약 데이터에 대한 답변을 받습니다.",
        "alram": alramData,
        "alramComment": "설비 알람분석에 대한 답변을 받습니다.",
        "effect": effectData,
        "effectComment": "설비 영향분석에 대한 답변을 받습니다."
    }

    return example