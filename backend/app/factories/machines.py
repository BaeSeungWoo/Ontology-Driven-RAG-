import json
from pathlib import Path

from fastapi import HTTPException, Request

FACTORY_IDS = ("yunam", "yulkok", "poongsan", "yunam_origin")


def history_factory_id(factory_id: str) -> str:
    return "yunam(origin)" if factory_id == "yunam_origin" else factory_id


def request_factory(request: Request | None = None) -> str:
    factory_id = request.headers.get("X-Factory-Id", "yunam") if request else "yunam"
    if factory_id not in FACTORY_IDS:
        raise HTTPException(400, "등록되지 않은 공장입니다.")
    return factory_id


def load_machine_info(request: Request | None = None, *, factory_id: str | None = None) -> dict:
    factory_id = factory_id or request_factory(request)
    if factory_id not in FACTORY_IDS:
        raise HTTPException(400, "등록되지 않은 공장입니다.")
    filename = "machine_info.json" if factory_id == "yunam_origin" else f"machine_info_{factory_id}.json"
    path = Path(__file__).parent / filename
    with path.open(encoding="utf-8-sig") as stream:
        return json.load(stream)
