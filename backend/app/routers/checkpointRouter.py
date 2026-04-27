from fastapi import APIRouter, HTTPException
from datetime import date, timedelta
from pydantic import BaseModel, Field
import json
import asyncio
from app.database import database
from app.database.daily_report_sections_spec import project_section_rows


from app.service import DailyReportService
from app.providers.daily_report_provider import get_daily_report_service

checkpointRouter = APIRouter(prefix="/api/checkpoint", tags=["checkpoint"])

class ReportSectionsRequest(BaseModel):
    date: date
    reportId: str = Field(min_length=1) #현재는 "OBI" 로 들어와서 string, 추후 reportId가 number형식이면 수정 고려
    locale: str = Field(min_length=2, max_length=10)  # 예: ko_KR
    config: str

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


def parse_checkpoint_context(context_raw) -> dict | None:
    """
    DAILY_REPORT_RESULT.CONTEXT_JSON을 checkpoint 응답 구조로 복원한다.
    """
    try:
        if context_raw is None:
            return None

        # getDailyReportResult() 결과셋 형식({"tb_0": [...]}) 처리
        if isinstance(context_raw, dict) and "tb_0" in context_raw:
            rows = context_raw.get("tb_0") or []
            first_row = rows[0] if isinstance(rows, list) and len(rows) > 0 else None
            if not isinstance(first_row, dict):
                return None
            context_raw = first_row.get("CONTEXT_JSON", first_row.get("CONTEXT"))

        context = json.loads(context_raw) if isinstance(context_raw, str) else context_raw
        if not isinstance(context, dict):
            return None

        required_keys = {"Section_01", "Section_02", "Section_03", "Section_04", "Section_05", "Section_06"}
        if not required_keys.issubset(context.keys()):
            return None

        return context
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

# ==============================
#   CheckPoint Test
# ==============================
@checkpointRouter.post("/getCheckPointSections")
async def getCheckPointSections(req: ReportSectionsRequest):
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
        stored_context_raw = database.getDailyReportResult(req.date, req.reportId, req.locale)
        stored_sections = parse_checkpoint_context(stored_context_raw)
        if stored_sections is not None:
            return stored_sections

        # DailyReportService 최초 실행시 메모리 초기화, 이후 재사용
        service = get_daily_report_service(req.config)
        # 전체 데이터
        report = get_daily_report(req.date, req.reportId, req.locale)
        # 전일 데이터
        previous_report_date = get_previous_report_date(req.date)
        previous_report = get_daily_report(previous_report_date, req.reportId, req.locale)

        # 2~6 섹션은 상호 독립이므로 병렬 실행
        section02_Data, section03_Data, section04_Data, section05_Data, section06_Data = await asyncio.gather(
            _build_production(report, previous_report, service),
            _build_shipping(report, service),
            _build_delivery(report, service),
            _build_quality(report, service),
            _build_equip(report, service),
        )

        # 1. 경영층 요약
        summaryData = {
            "product": section02_Data,
            "shipment": section03_Data,
            "delivery": section04_Data,
            "quality": section05_Data,
            "equip": section06_Data,
        }
        section01_Data = await _build_summary(report, service, summaryData)

        sections = {
            "Section_01": section01_Data,
            "Section_02": section02_Data,
            "Section_03": section03_Data,
            "Section_04": section04_Data,
            "Section_05": section05_Data,
            "Section_06": section06_Data,
        }

        database.saveDailyReportResult(
            req.date,
            req.reportId,
            req.locale,
            json.dumps(sections, ensure_ascii=False),
        )

        return sections
    
    except Exception as e:
        print(f"getReportSections error: {e}")
        raise HTTPException(
            status_code=500,
            detail="데일리리포트 - 통합 섹션 조회 중 오류가 발생했습니다.",
        )

# ==============================
#   01_ 경영층 요약 
# ==============================

async def _build_summary(report: dict, service: DailyReportService, summaryData: dict):
    """
    각 도메인의 summary[0] 한 행만 읽어 metrics로 변환한다.
    그리고 해당 metrics에 대한 코멘트와 핵심이슈를 LLM에게 얻어온다.
    """
    
    prodData = project_section_rows(report, "prod", "summary")
    shipData = project_section_rows(report, "ship", "summary")
    delvData = project_section_rows(report, "delv", "summary")
    qualData = project_section_rows(report, "qual", "summary")
    equipData = project_section_rows(report, "equip", "summary")
    attData = project_section_rows(report, "att", "summary")

    metrics = {
        "product": prodData[0] if prodData else {},
        "shipment": shipData[0] if shipData else {},
        "delivery": delvData[0] if delvData else {},
        "quality": qualData[0] if qualData else {},
        "equipment": equipData[0] if equipData else {},
        "attendance": attData[0] if attData else {},
    }

    comment = await service._generate_section("base", metrics)
    # result = service._validate_output(comment)

    # if not result["sections_ok"]:
    #     # 재시도 / 기본문구 / 에러처리 중 택1
    #     comment = "금일 운영 상태는 주의가 필요합니다. 주요 KPI 점검 및 즉시 조치가 필요합니다."

    test = {
        "base": report,
        "summary": summaryData
    }
    
    keyIssue = await service._generate_section("issue", test)

    summaryDatas = {
        "summary": metrics,
        "comment": comment,
        "keyIssue": keyIssue,
    }

    return summaryDatas

# ==============================
#   02_ 생산 현황 
# ==============================

async def _build_production(report: dict, past_report: dict, service: DailyReportService):
    """
    오늘 리포트(report)와 전일 리포트(past_report)를 받아, LLM에게 오늘/전일을 비교한
    생산요약 코멘트, 실적미달 코멘트(?), 설비 병목및 가동률에 대한 코멘트를 받는다.
    """
    
    # 2.1 생산요약 (영문 컬럼 변환본)
    summaryData = project_section_rows(report, "prod", "summary")
    summaryPrevData = project_section_rows(past_report, "prod", "summary")
    # summaryComment = await service._generate_section("base", summaryData)

    payload = {
        "current": summaryData,
        "previous": summaryPrevData
    }
    summaryComment = await service._generate_section("compare", payload)
    
    # 2.2 실적미달 LOT (영문 컬럼 변환본)
    underperformData = project_section_rows(report, "prod", "underperform")
    underperformComment = await service._generate_section("base", underperformData)

    # underperform의 데이터들 중 달성률 기준미달만 조회 예) 조건: 달성률 90% 미만 
    # underperformDataAll = project_section_rows(report, "prod", "underperform")
    # underperformData = [
    #     row for row in underperformDataAll
    #     if isinstance(row, dict) and to_float(row.get("achiveRate"), 100.0) < 90
    # ]
    

    # 2.3 설비 병목 및 가동률 (영문 컬럼 변환본)
    equipmentBottleneckData = project_section_rows(report, "prod", "equipmentBottleneck")
    bottleneckComment = await service._generate_section("base", equipmentBottleneckData)

    equipmentUtilizationData = project_section_rows(report, "prod", "equipmentUtilization")
    utilComment = await service._generate_section("base", equipmentUtilizationData)

    example = {
        "summary": summaryData,
        "summaryPrev": summaryPrevData,
        "summaryComment": summaryComment,
        "underperform": underperformData,
        "underperformComment": underperformComment,
        "equipmentBottleneck": equipmentBottleneckData,
        "equipmentUtilization": equipmentUtilizationData,
        "bottleneckComment": bottleneckComment,
        "utilComment": utilComment,
    }
    return example

# ==============================
#   03_ 출하 현황 
# ==============================

async def _build_shipping(report: dict, service: DailyReportService):
    """
    출하에 대한 요약, 상태, 지연원인을 LLM에게 전달해 답변을 받는다.
    """

    # 3.1 출하요약
    summaryData = project_section_rows(report, "ship", "summary")
    summaryComment = await service._generate_section("base", summaryData)
    # 3.2 출하상태 / 지연현황
    shipStateData = project_section_rows(report, "ship", "shipmentStatus")
    shipStateComment = await service._generate_section("base", shipStateData)
    # 3.3 지연원인 분석
    delayCauseData = project_section_rows(report, "ship", "delayCause")
    delayCauseComment = await service._generate_section("base", delayCauseData)

    example = {
        "summary": summaryData,
        "summaryComment": summaryComment,
        "shipState": shipStateData,
        "shipStateComment": shipStateComment,
        "delayCause": delayCauseData,
        "delayCauseComment": delayCauseComment
    }

    return example

# ==============================
#   04_ 납기 현황 
# ==============================

async def _build_delivery(report: dict, service: DailyReportService):
    """
    납기요약, 납기이슈
    """

    # 4.1 납기요약
    summaryData = project_section_rows(report, "delv", "summary")
    summaryComment = await service._generate_section("base", summaryData)
    # 4.2 납기이슈
    issueData = project_section_rows(report, "delv", "issues")
    issuesComment = await service._generate_section("base", issueData)


    example = {
        "summary": summaryData,
        "summaryComment": summaryComment,
        "issues": issueData,
        "issuesComment": issuesComment
    }

    return example

# ==============================
#   05_ 품질 현황 
# ==============================

async def _build_quality(report: dict, service: DailyReportService):
    """
    품질요약, 공정별 품질현황, 불량구성, 품질리스크 - 고객영향
    """

    # 5.1 품질요약
    summaryData = project_section_rows(report, "qual", "summary")
    summaryComment = await service._generate_section("base", summaryData)
    # 5.2 공정별 품질 현황
    processQualData = project_section_rows(report, "qual", "processQuality")
    processQualComment = await service._generate_section("base", processQualData)
    # 5.3 불량구성
    defectData = project_section_rows(report, "qual", "defectComposition")
    defectComment = await service._generate_section("base", defectData)
    # 5.4 품질 리스크 
    liskData = project_section_rows(report, "qual", "qualityIssues")
    liskComment = await service._generate_section("base", liskData)
    # 5.5 고객영향
    custData = project_section_rows(report, "qual", "customerImpact")
    custImpactComment = await service._generate_section("base", custData)

    example = {
        "summary": summaryData,
        "summaryComment": summaryComment,
        "processQual": processQualData,
        "processQualComment": processQualComment,
        "defect": defectData,
        "defectComment": defectComment,
        "lisk": liskData,
        "liskComment": liskComment,
        "custImpact": custData,
        "custImpactComment": custImpactComment
    }

    return example
# ==============================
#   06_ 설비 현황 
# ==============================

async def _build_equip(report: dict, service: DailyReportService):
    """
    설비 요약, 설비 알람분석, 설비 영향분석
    """

    # 6.1 설비 요약
    summaryData = project_section_rows(report, "equip", "statusSummary")
    summaryComment = await service._generate_section("base", summaryData)
    # 6.2 설비 알람 분석
    alramData = project_section_rows(report, "equip", "alarmAnalysis")
    alramComment = await service._generate_section("base", alramData)
    # 6.3 설비 영향 분석
    effectData = project_section_rows(report, "equip", "downtimeImpact")
    effectComment = await service._generate_section("base", effectData)

    example = {
        "summary": summaryData,
        "summaryComment": summaryComment,
        "alram": alramData,
        "alramComment": alramComment,
        "effect": effectData,
        "effectComment": effectComment
    }

    return example
