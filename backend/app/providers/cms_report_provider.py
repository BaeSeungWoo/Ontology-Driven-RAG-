from fastapi import HTTPException

from app.factories.config import CONFIGS
from app.service import CmsDailyReportService


CMS_REPORT_CONFIG_ID = "ollama_config"
cms_daily_report_services: dict[str, CmsDailyReportService] = {}

def get_cms_daily_report_service(
    config_id: str = CMS_REPORT_CONFIG_ID,
) -> CmsDailyReportService:
    if config_id not in cms_daily_report_services:
        config = CONFIGS.get(config_id)
        if not config:
            raise HTTPException(status_code=404, detail="LLM 설정을 찾을 수 없습니다.")
        cms_daily_report_services[config_id] = CmsDailyReportService(config)
    return cms_daily_report_services[config_id]
