from fastapi import APIRouter, HTTPException
from typing import Iterable
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

def find_row(report: dict, domain_cd: str, step_no: int = 1):
    """
    getDailyReport() 결과(tb_0 ~ tb_n)에서 DOMAIN_CD, STEP_NO 조건에 맞는 row 1개를 찾는다.
    """
    if not isinstance(report, dict):
        return None

    for tb_key, rows in report.items():
        if not str(tb_key).startswith("tb_") or not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, dict):
                continue

            if (
                str(row.get("DOMAIN_CD", "")).upper() == domain_cd
                and str(row.get("STEP_NO", "")).strip() == str(step_no)
            ):
                return row

    return None

def _pick_row_value(row: dict, keys: str | Iterable[str], default):
    """
    row에서 값 1개를 안전하게 조회한다.

    왜 필요한가:
    - DB 컬럼명이 환경/인코딩 이슈로 다르게 들어올 수 있다.
    - 단일 key가 아니라 key 후보 목록을 순서대로 검사하고,
      처음 찾은 유효값을 반환한다.

    동작:
    - keys가 문자열이면 단일 key로 처리
    - keys가 리스트/튜플이면 앞에서부터 순차 탐색
    - 값이 없으면 default 반환
    """
    key_list = [keys] if isinstance(keys, str) else list(keys)

    for key in key_list:
        if key in row and row.get(key) is not None:
            return row.get(key)

    return default

def project_row(row: dict | None, spec: dict):
    """
    원본 row를 프론트 응답 스키마로 변환한다.

    기존 의도:
    - report의 원본 컬럼(대부분 한글 컬럼명)을
      프론트에서 쓰는 영문 키로 투영(project)한다.
    - 각 필드마다 형변환(to_int/to_float/to_str)과 기본값을 함께 적용한다.

    spec 형식:
      {
        "eng_key": ("kor_key" 또는 ["alias1", "alias2"], caster, default)
      }
    """
    if row is None:
        return {eng: default for eng, (_, _, default) in spec.items()}

    out = {}
    for eng, (kor_keys, caster, default) in spec.items():
        raw = _pick_row_value(row, kor_keys, default)
        out[eng] = caster(raw, default)

    return out

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
        stored_context_raw = database.getDailyReportResult(req.date, req.reportId, req.locale)
        sections = parse_report_context(stored_context_raw)
        
        if sections is None:
            report = get_daily_report(req.date, req.reportId, req.locale)
            # summary = _build_summary_section(report)
            # anomaly_action = _build_anomaly_action_section(report)
            metrics = _build_metrics(report)
            # analysis = _build_analysis_section(report)
            sections = build_report_context(
                # summary=summary,
                # anomaly_action=anomaly_action,
                metrics=metrics,
                # analysis=analysis,
            )
            database.saveDailyReportResult(
                req.date,
                req.reportId,
                req.locale,
                json.dumps(sections, ensure_ascii=False),
            )

        return {
            # "summary": sections.get("summary"),
            # "anomalyAction": sections.get("anomalyAction"),
            "metrics": sections.get("metrics"),
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
    return {
        "product": _build_product(report),
        "shipment": _build_shipment(report),
        "delivery": _build_delivery(report),
        "quality": _build_quality(report),
        "equipment": _build_equipment(report),
        "attendance": _build_attendance(report),
    }

def _build_product(report: dict):
    row = find_row(report, domain_cd="PROD", step_no=1)
    spec = {
        "runningEquipQty": (["가동설비수"], to_int, 0),
        "planQty": (["계획수량"], to_int, 0),
        "achiveRate": (["달성률"], to_float, 0.0),
        "qty": (["실적수량"], to_int, 0),
        "totalEquipQty": (["총설비수"], to_int, 0),
    }
    return project_row(row, spec)

def _build_shipment(report: dict):
    row = find_row(report, domain_cd="SHIP", step_no=1)
    spec = {
        "planQty": (["계획수량"], to_int, 0),
        "shipQty": (["출하수량"], to_int, 0),
        "shipAmt": (["출하금액"], to_int, 0),
        "delayQty": (["지연건수"], to_int, 0),
        "leadtimeAVG": (["평균리드타임"], to_int, 0),
    }
    return project_row(row, spec)

def _build_delivery(report: dict):
    row = find_row(report, domain_cd="DELV", step_no=1)
    spec = {
        "totalCnt": (["전체건수"], to_int, 0),
        "passCnt": (["정상건수"], to_int, 0),
        "dangerCnt": (["위험건수"], to_int, 0),
        "delayCnt": (["지연건수"], to_int, 0),
        "delvRate": (["납기율"], to_float, 0.0),
    }
    return project_row(row, spec)

def _build_quality(report: dict):
    row = find_row(report, domain_cd="QUAL", step_no=1)
    spec = {
        "totalQty": (["총검사수량"], to_int, 0),
        "qty": (["양품수량"], to_int, 0),
        "defectQty": (["불량수량"], to_int, 0),
        "defectRate": (["불량률"], to_float, 0.0),
        "ppm": (["PPM"], to_int, 0),
    }
    return project_row(row, spec)

def _build_equipment(report: dict):
    row = find_row(report, domain_cd="EQUIP", step_no=1)
    spec = {
        "totalEquipQty": (["전체설비수"], to_int, 0),
        "runningEquipQty": (["가동설비수"], to_int, 0),
        "runningRate": (["가동률"], to_float, 0),
        "alarmEquipQty": (["알람설비수"], to_int, 0),
        "alarmCnt": (["알람건수"], to_int, 0),
        "status": (["설비상태"], to_str, "정상"),
    }
    return project_row(row, spec)

def _build_attendance(report: dict):
    row = find_row(report, domain_cd="ATT", step_no=1)
    spec = {
        "total": (["총인원"], to_int, 0),
        "work": (["출근"], to_int, 0),
        "absence": (["결근"], to_int, 0),
        "overtime": (["잔업"], to_int, 0),
    }
    return project_row(row, spec)

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
