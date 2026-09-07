from fastapi import HTTPException

from app.factories.config import CONFIGS
from app.service import MesDailyReportService


MES_REPORT_CONFIG_ID = "ollama_config"
mes_daily_report_services: dict[str, MesDailyReportService] = {}


def get_mes_daily_report_service(
    config_id: str = MES_REPORT_CONFIG_ID,
) -> MesDailyReportService:
    if config_id not in mes_daily_report_services:
        config = CONFIGS.get(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="LLM 설정을 찾을 수 없습니다.")
        mes_daily_report_services[config_id] = MesDailyReportService(config)
    return mes_daily_report_services[config_id]
