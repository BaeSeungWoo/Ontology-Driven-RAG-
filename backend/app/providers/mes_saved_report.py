import asyncio
import logging
from datetime import date, datetime

from app.database import database, mes_report_store as store
from app.factories.config import CONFIGS
from app.providers.mes_report_provider import get_mes_daily_report_service

logger = logging.getLogger(__name__)


def validate_view_date(views, report_date):
    # These cards describe the report day; trend/forecast rows span other dates.
    for key in ("mes2-card-production-result", "mes2-card-delivery-risk"):
        rows = views.get(key, [])
        if not rows:
            raise ValueError("리포트 기준일을 확인할 데이터가 없습니다.")
        value = rows[0].get("REPORT_DATE")
        if isinstance(value, datetime):
            value = value.date()
        elif not isinstance(value, date):
            value = date.fromisoformat(str(value)[:10])
        if value != report_date:
            raise ValueError("조회 데이터와 리포트 기준일이 일치하지 않습니다.")


async def generate_saved_report(token, config, report_date=store.REPORT_DATE):
    async def generate():
        views = await asyncio.to_thread(database.getMesDashboardViews)
        validate_view_date(views, report_date)
        # Persist the data first so charts are available while the LLM runs.
        await asyncio.to_thread(store.save_report, token, None, views, False, report_date)

        async def build(model):
            return await get_mes_daily_report_service(model).generate_report(
                views["mes2-production-trend-14d"], views["mes2-card-delivery-risk"],
                views["mes2-delivery-risk-detail"], views["machine-operation-rate-weekly"],
                views["mes2-quality-instrument-management"],
            )

        try:
            report = await asyncio.wait_for(build(config), timeout=240)
        except Exception:
            if config != "vllm_config":
                raise
            logger.warning("MES vLLM failed; retrying with Ollama", exc_info=True)
            await asyncio.to_thread(store.set_model, token, "ollama_config", CONFIGS["ollama_config"].llm.model_name, report_date)
            report = await build("ollama_config")
        await asyncio.to_thread(store.save_report, token, report, views, True, report_date)

    try:
        await asyncio.wait_for(generate(), timeout=540)
    except Exception:
        logger.exception("MES saved report generation failed")
        await asyncio.to_thread(store.fail_report, token, "리포트 생성에 실패했습니다. 다시 생성해 주세요.", report_date)
