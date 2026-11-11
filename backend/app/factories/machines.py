import json
from pathlib import Path

from fastapi import HTTPException, Request

FACTORY_IDS = ("yunam", "yulkok", "poongsan", "waff", "yunam_origin")


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
    return read_machine_info(Path(__file__).parent / filename)


def read_machine_info(path: Path) -> dict:
    with path.open(encoding="utf-8-sig") as stream:
        machines = json.load(stream)
    for code, info in machines.items():
        names = info["machine_name"]
        if isinstance(names, list):
            if not names or not all(isinstance(name, str) and name.strip() for name in names):
                raise ValueError(f"{path.name}: {code}의 장비명 목록을 확인해 주세요.")
            info["machine_name"] = names[0]
            info["machine_aliases"] = names[1:]
    return machines
