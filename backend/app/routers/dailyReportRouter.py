from fastapi import APIRouter, HTTPException
from datetime import date
from pydantic import BaseModel, Field
import json

from app.database import database

dailyReportRouter = APIRouter(prefix="/api/dailyReport", tags=["dailyReport"])

class ReportSectionsRequest(BaseModel):
    date: date
    reportId: str = Field(min_length=1) #현재는 "OBI" 로 들어와서 string, 추후 reportId가 number형식이면 수정 고려
    locale: str = Field(min_length=2, max_length=10)  # 예: ko_KR

# ==============================
#   공통 유틸 함수
# ==============================
def to_int(value, default=0):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default

def to_float(value, default=0.0):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default

def to_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()

def get_daily_report(report_date: date, report_id: str, locale: str) -> dict:
    """
    데일리 리포트 원본을 1회 조회하고, 비정상 응답이면 예외를 발생시킨다.
    """
    report = database.getDailyReport(report_date, report_id, locale)
    if not isinstance(report, dict):
        raise ValueError("daily report response is not dict")
    return report

# ==============================
#   일자별 리포트 최초 실행 결과를 저장해 LLM 재호출을 방지
# ==============================
def build_report_context(*, metrics: dict, summary=None, anomaly_action=None, analysis=None) -> dict:
    """
    섹션 결과를 단일 context(JSON 저장 대상)로 묶는다.
    """
    return {
        "summary": summary,
        "anomalyAction": anomaly_action,
        "metrics": metrics,
        "analysis": analysis,
    }

def parse_report_context(context_raw) -> dict | None:
    """
    DAILY_REPORT_RESULT.CONTEXT_JSON을 API 응답 스키마로 복원한다.
    - str이면 JSON 파싱
    - dict면 그대로 사용
    - 스키마 누락 필드는 기본값으로 보강
    """
    try:
        if context_raw is None:
            return None

        # getDailyReportResult()가 result set 형식({"tb_0": [...]})으로 반환되는 경우
        if isinstance(context_raw, dict) and "tb_0" in context_raw:
            rows = context_raw.get("tb_0") or []
            first_row = rows[0] if isinstance(rows, list) and len(rows) > 0 else None
            if not isinstance(first_row, dict):
                return None
            context_raw = first_row.get("CONTEXT_JSON", first_row.get("CONTEXT"))

        context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        if not isinstance(context, dict):
            return None

        return {
            "summary": context.get("summary"),
            "anomalyAction": context.get("anomalyAction"),
            "metrics": context.get("metrics") if isinstance(context.get("metrics"), dict) else _build_metrics({}),
            "analysis": context.get("analysis"),
        }
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


# ==============================
#   00_ 통합 호출
# ==============================
@dailyReportRouter.post("/getReportSections")
def getReportSections(req: ReportSectionsRequest):
    """
    데일리 리포트 전체 섹션(1,2,3,4)을 한 번에 반환한다.
    - DB의 getDailyReport()는 이 요청 안에서 1회만 호출한다.
    """
    try:
        # 1. getDailyReportResult 호출.
        # 2. 결과가 존재한다면 이 데이터의 context_json을 분해하여 데이터를 return
        # 3. 결과가 없다면 기존 섹션을 호출하여 llm의 답변을 얻어내고, 이 결과를 하나로 묶어 context_json을 만들어 
        #   DAILY_REPORT_RESULT 에 저장
        # stored_context_raw = database.getDailyReportResult(req.date, req.reportId, req.locale)
        # sections = parse_report_context(stored_context_raw)
        
        # if sections is None:
        #     report = get_daily_report(req.date, req.reportId, req.locale)
        #     # summary = _build_summary_section(report)
        #     # anomaly_action = _build_anomaly_action_section(report)
        #     metrics = _build_metrics(report)
        #     # analysis = _build_analysis_section(report)
        #     sections = build_report_context(
        #         # summary=summary,
        #         # anomaly_action=anomaly_action,
        #         metrics=metrics,
        #         # analysis=analysis,
        #     )
        #     database.saveDailyReportResult(
        #         req.date,
        #         req.reportId,
        #         req.locale,
        #         json.dumps(sections, ensure_ascii=False),
        #     )

        return {
            # "summary": sections.get("summary"),
            # "anomalyAction": sections.get("anomalyAction"),
            # "metrics": sections.get("metrics"),
            # "analysis": sections.get("analysis"),
            # "meta": sections.get("meta"),
        }
    
    except Exception as e:
        print(f"getReportSections error: {e}")
        raise HTTPException(
            status_code=500,
            detail="데일리리포트 - 통합 섹션 조회 중 오류가 발생했습니다.",
        )

# ==============================
#   01_ 전일 종합 요약
# ==============================
def _build_summary_section(report: dict):
    """
    01 섹션(전일 종합 요약) 응답 생성.
    """

    # TODO: report 전체 원본을 컨텍스트로 LLM 요약 결과를 text/figures에 반영

    return {
        "text": "",
        "figures": [
            {"name": "", "value": 0},
            {"name": "", "value": 0},
            {"name": "", "value": 0},
        ],
    }

# ==============================
#   02_ 이상 징후 및 경고 / 금일 우선 Action Items
# ==============================
def _build_anomaly_action_section(report: dict, pastReport: dict):
    """
    02 섹션(이상 징후/액션) 응답 생성.
    LLM이 평균/과거 데이터와 현재 report 비교를 통해 문제점과 즉시조치사항을 한다.
    """
    
    # TODO: 현재 report와 이전 평균/과거 데이터(pastReport) 비교 후 
    # LLM으로 이상 징후 및 경고(anomaly) / 당일 조치사항 (action) 을 얻어오는 로직 필요

    return {
        "anomaly": [
            string,
            string,
            ...
        ],
        "action": [
            string,
            string,
            ...
        ],
    }

# ==============================
#   03_ 핵심 지표 6 DOMAINS (생산/출하/납기/품질/설비/근태)
# ==============================
def _build_metrics(report: dict):
    """
    각 도메인의 summary[0] 한 행만 읽어 metrics로 변환한다.
    """
    return ()

# ==============================
#   04_ 원인 분석 / 추천 조치
# ==============================
def _build_analysis_section(report: dict):
    """
    04 섹션(원인 분석/조치 제안) 응답 생성.
    report 데이터와 과거(혹은 평균) 데이터를 비교하여 LLM에게 문제점과 발생원인, 원인종합요약, 추천조치를 얻어온다.
    """

    # TODO: 이전 평균 데이터(또는 과거n일) 와 비교 후 
    # LLM으로 각 problem과 그 원인인 cause들, 이에 대한 요약과 추천조치를 얻어오는 로직 필요
    
    return [
        {
            "problem": {
                "cause": [],
                "result": {
                    "summary": "",
                    "action": "",
                },
            },
        },
        {
            "problem": {
                "cause": [],
                "result": {
                    "summary": "",
                    "action": "",
                },
            },
        },
        ...
    ]

# ==============================
#   CheckPoint Test
# ==============================
@dailyReportRouter.post("/getCheckPointSections")
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
        # 1. 경영층 요약
        # 카드 데이터
        summary = _build_metrics(report)
        # 핵심 이슈
        keyIssue = _build_keyIssue(report)
        return {
            "report": report,
            
            "Section_01": {
                "summary": summary,
                "keyIssue": keyIssue,
            },
            # "Section_02": {

            # },
            
        }
    
    except Exception as e:
        print(f"getReportSections error: {e}")
        raise HTTPException(
            status_code=500,
            detail="데일리리포트 - 통합 섹션 조회 중 오류가 발생했습니다.",
        )

def _build_keyIssue(report: dict):
    """
    전체 데이터(report)를 LLM에게 주고 핵심이슈 3개에 대한 출력포맷을 강제한다.
    답변이 string | string[] 구조로 올것을 기대함
    """

    # TODO: 전체 데이터를 LLM에게 보내 핵심 이슈 최대 3개를 얻어오는 로직
    # result = logic(report)
    
    testResult = [
        "[설비] CNC-03 호기 스핀들 이상진동 알람 3회 발생 → 생산 차질 약 120분, 납기 리스크 확산",
        "[품질] 도장공정 불량률 3.1% (목표의 2배) → LOT 2건 전수검사 진행 중",
        "[납기] 거래처 A사 주문 4건 중 2건 납기 위험 단계 진입 → 생산순위 재조정 필요"
    ]
    return testResult
