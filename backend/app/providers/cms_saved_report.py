import asyncio
import logging

from app.database import database, cms_report_store as store
from app.providers.cms_report_provider import get_cms_daily_report_service
from app.factories.config import CONFIGS

logger = logging.getLogger(__name__)


async def generate_saved_report(token, config, report_date=store.REPORT_DATE):
    async def generate():
        views = await asyncio.to_thread(database.getCmsDashboardViews)
        service = get_cms_daily_report_service(config)
        report = await service.generate_report(
            views["daily-planned-rate"], views["hourly-rate"], views["daily-alarm-summary"],
            views["alarm-machine-top3"], views["longest-alarm-top3"], with_summary=False,
        )
        if report["weeklyPlannedRates"][-1]["workDate"] != report_date.isoformat():
            raise ValueError("조회 데이터와 리포트 기준일이 일치하지 않습니다.")
        await asyncio.to_thread(store.save_report, token, report, views, False, report_date)
        try:
            report["executiveSummary"] = await service.generate_summary(report)
        except Exception:
            if config != "vllm_config":
                raise
            logger.warning("CMS vLLM summary failed; retrying with Ollama", exc_info=True)
            await asyncio.to_thread(store.set_model, token, "ollama_config", CONFIGS["ollama_config"].llm.model_name, report_date)
            report["executiveSummary"] = await get_cms_daily_report_service("ollama_config").generate_summary(report)
        await asyncio.to_thread(store.save_report, token, report, views, True, report_date)

    try:
        await asyncio.wait_for(generate(), timeout=540)
    except Exception:
        logger.exception("CMS saved report generation failed")
        await asyncio.to_thread(store.fail_report, token, "리포트 생성에 실패했습니다. 다시 생성해 주세요.", report_date)
