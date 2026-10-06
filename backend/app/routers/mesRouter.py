import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Response, BackgroundTasks
from typing import Any, Literal

from pydantic import BaseModel

from app.database import database
from app.database import mes_report_store as store
from app.factories.config import CONFIGS
from app.providers.mes_saved_report import generate_saved_report
from app.html_to_pdf import render_html_pdf
from app.providers.mes_report_provider import (
    MES_REPORT_CONFIG_ID,
    get_mes_daily_report_service,
)


mesRouter = APIRouter(prefix="/api/mes", tags=["mes"])


class MesSavedReportRequest(BaseModel):
    config: Literal["ollama_config", "vllm_config"] = "vllm_config"
    force: bool = False
    reportDate: date = store.REPORT_DATE


def validate_report_date(report_date: date):
    yesterday = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=1)
    if report_date > yesterday:
        raise HTTPException(status_code=422, detail=f"리포트 날짜는 {yesterday.isoformat()}까지 선택할 수 있습니다.")


@mesRouter.get("/saved-report")
def get_saved_report(reportDate: date = store.REPORT_DATE):
    validate_report_date(reportDate)
    return {"savedReport": store.get_report(reportDate)}


@mesRouter.post("/saved-report")
async def start_saved_report(req: MesSavedReportRequest, background_tasks: BackgroundTasks):
    validate_report_date(req.reportDate)
    if req.reportDate != store.REPORT_DATE:
        saved = await asyncio.to_thread(store.get_report, req.reportDate)
        if saved is not None and not req.force:
            return {"savedReport": saved}
        raise HTTPException(status_code=409, detail="현재 테스트 데이터는 2026-08-20 기준입니다. 다른 날짜는 저장본 조회만 가능합니다.")
    token = await asyncio.to_thread(store.claim_report, req.config, CONFIGS[req.config].llm.model_name, req.force, req.reportDate)
    if token is not None:
        background_tasks.add_task(generate_saved_report, token, req.config, req.reportDate)
    return {"savedReport": await asyncio.to_thread(store.get_report, req.reportDate)}


class MesReportRequest(BaseModel):
    config: str = MES_REPORT_CONFIG_ID
    productionTrendRows: list[dict[str, Any]]
    deliveryRiskCardRows: list[dict[str, Any]]
    deliveryRiskDetailRows: list[dict[str, Any]]
    equipmentWeeklyRows: list[dict[str, Any]]
    qualityInstrumentRows: list[dict[str, Any]]


class MesPdfRequest(BaseModel):
    html: str


@mesRouter.post("/report")
async def generate_mes_report(req: MesReportRequest):
    try:
        service = get_mes_daily_report_service(req.config)

        return {
            "report": await service.generate_report(
                req.productionTrendRows,
                req.deliveryRiskCardRows,
                req.deliveryRiskDetailRows,
                req.equipmentWeeklyRows,
                req.qualityInstrumentRows,
            )
        }
    except Exception as e:
        print(f"MES report error: {e}")
        raise HTTPException(
            status_code=500,
            detail="MES 리포트를 생성하지 못했습니다.",
        )


@mesRouter.post("/export-pdf")
def export_mes_pdf(req: MesPdfRequest):
    try:
        return Response(content=render_html_pdf(req.html), media_type="application/pdf")
    except Exception as e:
        print(f"MES PDF export error: {e}")
        raise HTTPException(
            status_code=500,
            detail="MES PDF를 생성하지 못했습니다.",
        )


@mesRouter.get("/dashboard")
def get_dashboard_views():
    try:
        return {"views": database.getMesDashboardViews()}
    except Exception as e:
        print(f"MES dashboard views error: {e}")
        raise HTTPException(
            status_code=500,
            detail="MES 데이터를 불러오지 못했습니다.",
        )


@mesRouter.get("/dashboard/{view_key}")
def get_dashboard_view(view_key: str):
    try:
        return {"rows": database.getMesDashboardView(view_key)}
    except ValueError:
        raise HTTPException(status_code=404, detail="지원하지 않는 MES 뷰입니다.")
    except Exception as e:
        print(f"MES dashboard view error: view_key={view_key}, error={e}")
        raise HTTPException(
            status_code=500,
            detail="MES 데이터를 불러오지 못했습니다.",
        )
