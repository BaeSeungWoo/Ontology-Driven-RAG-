from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import json
import traceback
import os
from pathlib import Path
from app.database import database
from app.security.validate_code import resolve_request_code, validate_code
from dotenv import load_dotenv

historyRouter = APIRouter(prefix="/api/history", tags=["history"])

def load_machine_info() -> dict:
    json_path = Path(__file__).resolve().parent.parent / "factories" / "machine_info.json"
    with json_path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def set_history_code(ctx) -> str:
    if ctx.is_main_server:
        return "ALL"   # 또는 프로시저가 이해하는 다른 전체조회 값
    if not ctx.request_machine_code:
        raise HTTPException(status_code=403, detail="IP에 매핑된 장비가 없습니다.")
    return ctx.request_machine_code


@historyRouter.post("/getHistory")
def getHistoryList(client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    machine_code = set_history_code(ctx)
    try:
        history_list = database.getHistoryList(machine_code)
        json_data = []

        for row in history_list:
            json_data.append(
                {
                    "sessionId": row[0],
                    "questioner": row[1],
                    "title": row[2],
                    "llmModel": row[3],
                    "llmMode": row[4],
                    "promptNo": row[5],
                    "createdAt": row[6],
                    "updatedAt": row[7],
                    "promptName": row[8],
                }
            )

        return json_data
    except Exception as e:
        print(f"get_history_list error: {e}")
        raise HTTPException(
            status_code=500,
            detail="대화 이력 목록 조회 중 오류가 발생했습니다.",
        )


class HistoryPaginationRequest(BaseModel):
    page: int
    page_size: int


class HistoryQuestionerRequest(BaseModel):
    questioner: str | None = None
    page: int | None = None
    page_size: int | None = None


def _row_to_history_json(row):
    return {
        "sessionId": row[0],
        "questioner": row[1],
        "title": row[2],
        "llmModel": row[3],
        "llmMode": row[4],
        "promptNo": row[5],
        "createdAt": row[6],
        "updatedAt": row[7],
        "promptName": row[8],
    }


def _sanitize_page(page: int, page_size: int):
    safe_page = max(1, int(page))
    safe_page_size = max(1, int(page_size))
    return safe_page, safe_page_size


def _paginate_rows(rows, page: int, page_size: int):
    total_count = len(rows)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    safe_page = min(page, total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return rows[start:end], total_count, total_pages, safe_page


@historyRouter.post("/getHistoryPagination")
def getHistoryPagination(req: HistoryPaginationRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    machine_code = set_history_code(ctx)
    try:
        page, page_size = _sanitize_page(req.page, req.page_size)
        result = database.getHistoryPagination(page, page_size, machine_code)
        rows = result.get("rows", [])
        total_count = int(result.get("total_count", 0))
        total_pages = max(1, int(result.get("total_pages", 1)))
        safe_page = max(1, int(result.get("page", page)))
        safe_page_size = max(1, int(result.get("page_size", page_size)))

        return {
            "rows": [_row_to_history_json(row) for row in rows],
            "total_count": total_count,
            "total_pages": total_pages,
            "page": safe_page,
            "page_size": safe_page_size,
        }
    except Exception as e:
        print(f"getHistoryPagination error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="대화 이력 페이지 조회 중 오류가 발생했습니다.",
        )


@historyRouter.post("/getHistoryQuestioner")
def getHistoryQuestioner(req: HistoryQuestionerRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    machine_code = set_history_code(ctx)
    try:
        # 요청 바디가 {} 인 경우: 질문자별 count 목록 반환
        if req.questioner is None:
            count_rows = database.getHistoryQuestionerCounts(machine_code)
            return [
                {"questioner": row[0] if row[0] else "-", "count": int(row[1]) if row[1] is not None else 0}
                for row in count_rows
            ]

        # 요청 바디에 questioner/page/page_size가 있는 경우: 질문자 필터 페이지 조회
        if req.page is None or req.page_size is None:
            raise HTTPException(
                status_code=400,
                detail="questioner 페이지 조회 시 page, page_size가 필요합니다.",
            )

        page, page_size = _sanitize_page(req.page, req.page_size)
        target_questioner = req.questioner.strip() if req.questioner else "-"
        result = database.getHistoryQuestioner(target_questioner, page, page_size, machine_code)
        rows = result.get("rows", [])
        total_count = int(result.get("total_count", 0))
        total_pages = max(1, int(result.get("total_pages", 1)))
        safe_page = max(1, int(result.get("page", page)))
        safe_page_size = max(1, int(result.get("page_size", page_size)))

        return {
            "rows": [_row_to_history_json(row) for row in rows],
            "total_count": total_count,
            "total_pages": total_pages,
            "page": safe_page,
            "page_size": safe_page_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"getHistoryQuestioner error: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail="질문자 이력 조회 중 오류가 발생했습니다.",
        )


class CreateSessionRequest(BaseModel):
    questioner: str
    title: str
    llm_model: str
    llm_mode: str
    prompt_no: int


class CreateSessionResponse(BaseModel):
    result: str
    session_id: int


class CreateMessageRequest(BaseModel):
    session_id: int
    role: str
    content: str = ""


class CreateMessageResponse(BaseModel):
    result: str
    message_id: int


class UpdateMessageRequest(BaseModel):
    content: str
    metadata: dict | None = None


class UpdateMessageResponse(BaseModel):
    result: str


class GetMessagesRequest(BaseModel):
    session_id: int


@historyRouter.post("/newSession", response_model=CreateSessionResponse)
def createSession(req: CreateSessionRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    machine_code = set_history_code(ctx)
    try:
        session_id = database.createSession(
            req.questioner,
            req.title,
            req.llm_model,
            req.llm_mode,
            req.prompt_no,
            machine_code
        )
        return {"result": "success", "session_id": session_id}
    except Exception as e:
        print("[history/newSession] error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"newSession error: {str(e)}")


@historyRouter.delete("/sessions/{session_id}")
def deleteChatSession(session_id: int, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    session_info = database.getChatSessionInfo(session_id)
    validate_code(ctx, session_info)

    try:
        database.deleteChatSession(session_id)
        return {"result": "success"}
    except Exception as e:
        print("[history/sessions] delete error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"deleteChatSession error: {str(e)}")


@historyRouter.post("/getMessages")
def getMessages(req: GetMessagesRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    session_info = database.getChatSessionInfo(req.session_id)
    validate_code(ctx, session_info)

    try:
        rows = database.getChatMessagesBySession(req.session_id)
        json_data = []
        for row in rows:
            created_at = row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4])
            metadata_raw = row[8] if len(row) > 8 else None
            metadata = None
            if metadata_raw:
                try:
                    metadata = json.loads(metadata_raw) if isinstance(metadata_raw, str) else metadata_raw
                except (TypeError, ValueError, json.JSONDecodeError):
                    metadata = None

            json_data.append(
                {
                    "message_id": row[0],
                    "session_id": row[1],
                    "role": row[2],
                    "content": row[3],
                    "created_at": created_at,
                    "questioner": row[5],
                    "model": row[6],
                    "llm_mode": row[7],
                    "metadata": metadata,
                }
            )
        return json_data
    except Exception as e:
        print("[history/getMessages] error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"getMessages error: {str(e)}")


@historyRouter.post("/messages", response_model=CreateMessageResponse)
def createMessage(req: CreateMessageRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    session_info = database.getChatSessionInfo(req.session_id)
    validate_code(ctx, session_info)

    try:
        if req.role not in ("user", "assistant"):
            raise HTTPException(status_code=400, detail="role must be 'user' or 'assistant'")

        message_id = database.createChatMessage(req.session_id, req.role, req.content)
        return {"result": "success", "message_id": message_id}
    except HTTPException:
        raise
    except Exception as e:
        print("[history/messages] create error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"createMessage error: {str(e)}")


@historyRouter.put("/messages/{message_id}", response_model=UpdateMessageResponse)
def updateMessage(message_id: int, req: UpdateMessageRequest, client_request: Request):
    machine_info = load_machine_info()
    ctx = resolve_request_code(
        request=client_request,
        machines=machine_info,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    session_id = database.getSessionIdByMessageId(message_id)
    if session_id is None:
        raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")

    session_info = database.getChatSessionInfo(session_id)
    validate_code(ctx, session_info)

    try:
        metadata_json = json.dumps(req.metadata, ensure_ascii=False) if req.metadata is not None else None
        database.updateChatMessage(message_id, req.content, metadata_json)
        return {"result": "success"}
    except Exception as e:
        print("[history/messages] update error:", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"updateMessage error: {str(e)}")
