from dataclasses import dataclass
from fastapi import Request, HTTPException

@dataclass
class RequestCode:
    user_ip: str
    request_machine_code: str | None
    is_main_server: bool

# 요청자 ip 추출
def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "Unknown IP"

# ip별 해당 장비 코드 추출
def resolve_request_code(request: Request, machines: dict, main_server_ips: set[str]) -> RequestCode:
    user_ip = get_client_ip(request)

    request_machine_code = None
    for code, m_info in machines.items():
        if m_info.get("machine_ip") == user_ip:
            request_machine_code = code
            break

    return RequestCode(
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

    if ctx.is_main_server:
        if not session_machine_code:
            raise HTTPException(status_code=400, detail="세션 장비코드가 없습니다.")
        return session_machine_code

    if not request_machine_code:
        raise HTTPException(status_code=403, detail="IP에 매핑된 장비가 없습니다.")

    if request_machine_code != session_machine_code:
        raise HTTPException(status_code=403, detail="다른 장비의 질문이력에는 접근이 불가능합니다.")

    return session_machine_code