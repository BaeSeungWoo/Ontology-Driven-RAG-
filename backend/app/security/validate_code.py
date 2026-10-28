from dataclasses import dataclass
import logging
from fastapi import Request, HTTPException
from pipeline.ingestion.machine_resolver import machine_documents
from app.factories.machines import history_factory_id, request_factory

@dataclass
class RequestCode:
    user_ip: str
    request_machine_code: str | None
    is_main_server: bool
    machine_codes: frozenset[str] | None = None
    factory_id: str = "yunam"


def require_machine_documents(code, machines):
    if code != "ALL" and not machine_documents(machines.get(code, {})):
        raise HTTPException(status_code=409, detail="매뉴얼이 등록되지 않아 준비 중인 장비입니다. 채팅을 사용할 수 없습니다.")


def session_machine_code(ctx, requested_code, machines):
    requested_code = (requested_code or "").strip()
    if requested_code == "ALL" and ctx.is_main_server:
        return "ALL"
    if requested_code:
        if not ctx.is_main_server and requested_code != ctx.request_machine_code:
            raise HTTPException(status_code=403, detail="다른 장비에는 접근이 불가능합니다.")
        if requested_code not in machines:
            raise HTTPException(status_code=400, detail="등록되지 않은 장비코드입니다.")
        require_machine_documents(requested_code, machines)
        return requested_code
    if ctx.request_machine_code:
        require_machine_documents(ctx.request_machine_code, machines)
        return ctx.request_machine_code
    if ctx.is_main_server:
        return "ALL"
    raise HTTPException(status_code=403, detail="IP에 매핑된 장비가 없습니다.")


def cms_machine_code(machine_code, requested_code, ctx, machines):
    requested_code = (requested_code or "").strip()
    if requested_code and not ctx.is_main_server and requested_code != ctx.request_machine_code:
        raise HTTPException(status_code=403, detail="다른 장비의 CMS에는 접근이 불가능합니다.")
    if machine_code and machine_code != "ALL":
        return machine_code
    if requested_code:
        if requested_code == "ALL" or requested_code not in machines:
            raise HTTPException(status_code=400, detail="등록되지 않은 CMS 장비코드입니다.")
        return requested_code
    return machine_code

# 요청자 ip 추출
def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "Unknown IP"

# ip별 해당 장비 코드 추출
def resolve_request_code(request: Request, machines: dict, main_server_ips: set[str]) -> RequestCode:
    user_ip = get_client_ip(request)
    main_server_ips = {ip.strip() for value in main_server_ips for ip in value.split(",") if ip.strip()}

    request_machine_code = None
    for code, m_info in machines.items():
        if m_info.get("machine_ip") == user_ip or user_ip in m_info.get("machine_ips", []):
            request_machine_code = code
            break

    logging.getLogger("uvicorn.error").info(
        "[machine_assignment] %s %s connection_ip=%r x_forwarded_for=%r resolved_ip=%r machine_code=%r",
        request.method,
        request.url.path,
        request.client.host if request.client else None,
        request.headers.get("X-Forwarded-For"),
        user_ip,
        request_machine_code,
    )

    return RequestCode(
        factory_id=request_factory(request),
        machine_codes=frozenset(machines),
        user_ip=user_ip,
        request_machine_code=request_machine_code,
        is_main_server=(
            "*" in main_server_ips
            or user_ip in main_server_ips
        ),
    )

# 세션 장비코드와 요청자 장비코드 비교
def validate_code(ctx, session_info) -> str:
    if session_info is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

    session_machine_code = (session_info.get("machine_code") or "").strip()
    request_machine_code = (ctx.request_machine_code or "").strip()

    if session_info.get("factory") != history_factory_id(ctx.factory_id):
        raise HTTPException(status_code=403, detail="다른 공장의 대화 이력에는 접근할 수 없습니다.")

    if ctx.is_main_server:
        if not session_machine_code:
            raise HTTPException(status_code=400, detail="세션 장비코드가 없습니다.")
        return session_machine_code

    if not request_machine_code:
        raise HTTPException(status_code=403, detail="IP에 매핑된 장비가 없습니다.")

    if request_machine_code != session_machine_code:
        raise HTTPException(status_code=403, detail="다른 장비의 질문이력에는 접근이 불가능합니다.")

    return session_machine_code
