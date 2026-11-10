import os

from fastapi import APIRouter, HTTPException, Request

from app.database import database
from app.factories.config import get_factory_config
from app.factories.machines import load_machine_info, request_factory
from app.core.machine_readiness import machine_readiness
from pipeline.ingestion.machine_resolver import machine_documents
from app.security.validate_code import resolve_request_code, session_machine_code

promptRouter = APIRouter(prefix="/api/prompts", tags=["prompts"])



def _machine_list_item(code, info, ctx):
    documents = set(machine_documents(info, "manual")) | set(machine_documents(info, "controller"))
    return {
        "machine_code": code,
        "machine_name": info["machine_name"],
        "machine_controller": info.get("machine_controller", ""),
        "machine_ver": info.get("machine_ver", ""),
        "is_assigned": code == ctx.request_machine_code,
        "has_documents": bool(machine_documents(info)),
        "readiness": "unchecked",
        "searchable_document_count": 0,
        "document_count": len(documents),
        "has_ladder": bool(machine_documents(info, "ladder")),
        "has_electrical": bool(machine_documents(info, "electrical")),
        "can_select": ctx.is_main_server or code == ctx.request_machine_code,
        "is_main_server": ctx.is_main_server,
    }


@promptRouter.get("/machines")
def get_machines(client_request: Request, llm_model: str = "vllm_config"):
    machines = load_machine_info(client_request)
    ctx = resolve_request_code(
        request=client_request, machines=machines,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    return [_machine_list_item(code, info, ctx) for code, info in machines.items()]


@promptRouter.get("/machines/{machine_code}/readiness")
def get_machine_readiness(machine_code: str, client_request: Request, llm_model: str = "vllm_config"):
    machines = load_machine_info(client_request)
    ctx = resolve_request_code(
        request=client_request, machines=machines,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    if not ctx.is_main_server and machine_code != ctx.request_machine_code:
        raise HTTPException(403, "다른 장비에는 접근이 불가능합니다.")
    if machine_code not in machines:
        raise HTTPException(404, detail={"message": "등록되지 않은 장비코드입니다.", "machine_code": machine_code})
    info = machines[machine_code]
    result = _machine_list_item(machine_code, info, ctx)
    if not machine_documents(info):
        state = {"readiness": "no_documents", "searchable_document_count": 0,
                 "document_count": 0, "has_ladder": False, "has_electrical": False}
    else:
        config = get_factory_config(llm_model, request_factory(client_request))
        state = machine_readiness(config, {machine_code: info})[machine_code]
    result.update(state)
    result["can_select"] = state["readiness"] in ("ready", "partial") or state["has_electrical"]
    if result["can_select"]:
        return result
    message = ("선택한 장비에 매뉴얼이 등록되지 않았습니다." if state["readiness"] == "no_documents"
               else "선택한 장비의 검색 데이터를 확인할 수 없습니다. 검색 DB를 확인해 주세요."
               if state["readiness"] == "check_failed" else "선택한 장비의 매뉴얼 검색 데이터가 없습니다.")
    raise HTTPException(409, detail={"message": message, "machine": result})


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
