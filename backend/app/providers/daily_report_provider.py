from fastapi import HTTPException

from app.factories.config import CONFIGS
from app.service import DailyReportService


daily_report_services: dict[str, DailyReportService] = {}


def get_daily_report_service(factory_id: str) -> DailyReportService:
    if factory_id not in daily_report_services:
        cfg = CONFIGS.get(factory_id)
        if not cfg:
            raise HTTPException(status_code=404, detail="해당 공장 설정을 찾을 수 없습니다.")
        daily_report_services[factory_id] = DailyReportService(cfg)
    return daily_report_services[factory_id]
