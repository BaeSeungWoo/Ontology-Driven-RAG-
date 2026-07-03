import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.database import database
from app.security.validate_code import resolve_request_code

promptRouter = APIRouter(prefix="/api/prompts", tags=["prompts"])


def load_machine_info() -> dict:
    json_path = Path(__file__).resolve().parent.parent / "factories" / "machine_info.json"
    with json_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


@promptRouter.post("/getPromptList")
def getPromptList(client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips=set([os.getenv("MSSQL_HOST")]),
    )

    try:
        prompt_list = database.getPromptList()
        json_data = []

        for row in prompt_list:
            json_data.append(
                {
                    "PROMPT_NO": row[0],
                    "PROMPT_NAME": row[1],
                    "PROMPT_TXT": row[2],
                    "CREATE_USER": row[3],
                    "SEL_YN": "N",
                }
            )

        return {
            "rows": json_data,
            "machine_code": ctx.request_machine_code,
            "machine_info": machine_info.get(ctx.request_machine_code) if ctx.request_machine_code else None,
            "is_main_server": ctx.is_main_server,
        }
    except Exception as e:
        print(f"get_prompt_list error: {e}")
        raise HTTPException(
            status_code=500,
            detail="프롬프트 목록 조회 중 오류가 발생했습니다.",
        )
