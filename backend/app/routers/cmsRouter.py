from fastapi import APIRouter, HTTPException
from typing import Literal

from pydantic import BaseModel, Field
from app.database import database
from app.providers.cms_report_provider import (
    CMS_REPORT_CONFIG_ID,
    get_cms_daily_report_service,
)

cmsRouter = APIRouter(prefix="/api/cms", tags=["cms"])


class CmsReportRequest(BaseModel):
    config: str = CMS_REPORT_CONFIG_ID


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
        views = database.getCmsDashboardViews()
        service = get_cms_daily_report_service(req.config)
        report = await service.generate_report(
            views["daily-planned-rate"],
            views["hourly-rate"],
            views["daily-alarm-summary"],
            views["alarm-machine-top3"],
            views["longest-alarm-top3"],
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
