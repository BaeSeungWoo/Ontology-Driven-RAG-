import asyncio
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Literal

from pydantic import BaseModel, Field
from app.database import database
from app.database import cms_report_store as store
from app.factories.config import CONFIGS
from app.providers.cms_saved_report import generate_saved_report
from app.providers.cms_report_provider import (
    CMS_REPORT_CONFIG_ID,
    get_cms_daily_report_service,
)

cmsRouter = APIRouter(prefix="/api/cms", tags=["cms"])


class CmsReportRequest(BaseModel):
    config: str = CMS_REPORT_CONFIG_ID
    views: dict[str, list[dict]] | None = None
    withSummary: bool = True


class CmsSavedReportRequest(BaseModel):
    config: Literal["ollama_config", "vllm_config"] = "vllm_config"
    force: bool = False
    reportDate: date = store.REPORT_DATE


def validate_report_date(report_date: date):
    yesterday = datetime.now(timezone(timedelta(hours=9))).date() - timedelta(days=1)
    if report_date > yesterday:
        raise HTTPException(status_code=422, detail="리포트 날짜는 어제까지 선택할 수 있습니다.")


@cmsRouter.get("/saved-report")
def get_saved_report(reportDate: date = store.REPORT_DATE):
    validate_report_date(reportDate)
    return {"savedReport": store.get_report(reportDate)}


@cmsRouter.post("/saved-report")
async def start_saved_report(req: CmsSavedReportRequest, background_tasks: BackgroundTasks):
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


class CmsChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class CmsChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    history: list[CmsChatMessage] = Field(default_factory=list)
    report: dict
    config: str = CMS_REPORT_CONFIG_ID

@cmsRouter.post("/report")
async def generate_cms_report(req: CmsReportRequest):
    try:
        views = req.views if req.views is not None else database.getCmsDashboardViews()
        service = get_cms_daily_report_service(req.config)
        report = await service.generate_report(
            views["daily-planned-rate"],
            views["hourly-rate"],
            views["daily-alarm-summary"],
            views["alarm-machine-top3"],
            views["longest-alarm-top3"],
            with_summary=req.withSummary,
        )
        return {
            "summary": report["executiveSummary"],
            "report": report,
        }
    except Exception as e:
        print(f"CMS daily report error: {e}")
        raise HTTPException(
            status_code=500,
            detail="CMS 전일 리포트를 불러오지 못했습니다.",
        )


@cmsRouter.post("/chat")
async def answer_cms_question(req: CmsChatRequest):
    try:
        service = get_cms_daily_report_service(req.config)
        answer = await service.answer_question(
            req.question,
            [{"role": message.role, "content": message.content} for message in req.history],
            req.report,
        )
        return {"answer": answer}
    except Exception as e:
        print(f"CMS chat error: {e}")
        raise HTTPException(
            status_code=500,
            detail="CMS 데이터 기반 답변을 생성하지 못했습니다.",
        )

@cmsRouter.get("/dashboard")
def get_dashboard_views():
    try:
        return {"views": database.getCmsDashboardViews()}
    except Exception as e:
        print(f"CMS dashboard views error: {e}")
        raise HTTPException(
            status_code=500,
            detail="CMS 데이터를 불러오지 못했습니다.",
        )

@cmsRouter.get("/dashboard/{view_key}")
def get_dashboard_view(view_key: str):
    try:
        return {"rows": database.getCmsDashboardView(view_key)}
    except ValueError:
        raise HTTPException(status_code=404, detail="지원하지 않는 CMS 뷰입니다.")
    except Exception as e:
        print(f"CMS dashboard view error: view_key={view_key}, error={e}")
        raise HTTPException(
            status_code=500,
            detail="CMS 데이터를 불러오지 못했습니다.",
        )
