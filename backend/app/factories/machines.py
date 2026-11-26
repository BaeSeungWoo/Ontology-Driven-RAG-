import json
import os
import re
from dotenv import load_dotenv
from pathlib import Path

from fastapi import HTTPException, Request

DATA_ROOT = Path(__file__).resolve().parents[3] / "pipeline/data"
load_dotenv(Path(__file__).resolve().parents[1] / ".env.back")


PROMPT_FACTORIES = {"yunam", "poongsan", "yulkok"}


def factory_ids():
    ids = [key.strip() for key in os.environ.get("FACTORY_IDS", "").split(",")]
    if any(not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", key) for key in ids) or len(set(ids)) != len(ids):
        raise ValueError(".env.back의 FACTORY_IDS에 서로 다른 공장 폴더명을 입력하세요.")
    return ids


def factory_options():
    options = []
    for key in factory_ids():
        path = DATA_ROOT / key / "factory.json"
        name = json.loads(path.read_text(encoding="utf-8-sig"))["display_name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{path}: display_name을 입력하세요.")
        options.append({"id": key, "name": name})
    return options


def history_factory_id(factory_id: str) -> str:
    return {"yunam_origin": "yunam(origin)", "3way": "graph_3way"}.get(factory_id, factory_id)


def request_factory(request: Request | None = None) -> str:
    default = factory_ids()[0]
    factory_id = request.headers.get("X-Factory-Id", default) if request else default
    if factory_id == "graph_3way":
        factory_id = "3way"
    if factory_id not in factory_ids():
        raise HTTPException(400, "등록되지 않은 공장입니다.")
    return factory_id


def load_machine_info(request: Request | None = None, *, factory_id: str | None = None) -> dict:
    factory_id = factory_id or request_factory(request)
    if factory_id not in factory_ids():
        raise HTTPException(400, "등록되지 않은 공장입니다.")
    filename = {
        "yunam_origin": "machine_info.json",
    }.get(factory_id, f"machine_info_{factory_id}.json")
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
