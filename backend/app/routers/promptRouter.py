import os

from fastapi import APIRouter, HTTPException, Request

from app.database import database
from app.factories.config import get_factory_config
from app.factories.machines import load_machine_info, request_factory
from app.core.machine_readiness import machine_readiness
from pipeline.ingestion.machine_resolver import machine_documents
from app.security.validate_code import resolve_request_code, session_machine_code

promptRouter = APIRouter(prefix="/api/prompts", tags=["prompts"])



@promptRouter.get("/machines")
def get_machines(client_request: Request, llm_model: str = "vllm_config"):
    config = get_factory_config(llm_model, request_factory(client_request))
    machines = config.machines
    readiness = machine_readiness(config, machines)
    ctx = resolve_request_code(
        request=client_request,
        machines=machines,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    return [
        {
            "machine_code": code,
            "machine_name": info["machine_name"],
            "machine_controller": info.get("machine_controller", ""),
            "machine_ver": info.get("machine_ver", ""),
            "is_assigned": code == ctx.request_machine_code,
            "has_documents": bool(machine_documents(info)),
            **readiness[code],
            "can_select": (config.id not in {"yulkok", "poongsan"} or code in {
                "M001", "M002", "M003", "M004", "M005",
            }) and (ctx.is_main_server or code == ctx.request_machine_code) and (
                readiness[code]["readiness"] in ("ready", "partial") or readiness[code]["has_electrical"]),
            "is_main_server": ctx.is_main_server,
        }
        for code, info in machines.items()
    ]


@promptRouter.post("/getPromptList")
def getPromptList(client_request: Request, machine_code: str | None = None):
    machine_info = load_machine_info(client_request)
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    selected_code = session_machine_code(ctx, machine_code, machine_info) if machine_code else ctx.request_machine_code
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
            "machine_code": selected_code,
            "machine_info": machine_info.get(selected_code),
            "is_main_server": ctx.is_main_server,
        }
    except Exception as e:
        print(f"get_prompt_list error: {e}")
        raise HTTPException(
            status_code=500,
            detail="프롬프트 목록 조회 중 오류가 발생했습니다.",
        )
