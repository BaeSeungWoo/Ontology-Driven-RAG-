from fastapi import APIRouter, HTTPException
from typing import Any

from pydantic import BaseModel

from app.database import database
from app.providers.mes_report_provider import (
    MES_REPORT_CONFIG_ID,
    get_mes_daily_report_service,
)


mesRouter = APIRouter(prefix="/api/mes", tags=["mes"])


class MesReportRequest(BaseModel):
    config: str = MES_REPORT_CONFIG_ID
    productionTrendRows: list[dict[str, Any]]
    deliveryRiskCardRows: list[dict[str, Any]]
    deliveryRiskDetailRows: list[dict[str, Any]]
    equipmentWeeklyRows: list[dict[str, Any]]
    qualityInstrumentRows: list[dict[str, Any]]


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
