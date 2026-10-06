# backend/app/main.py

import json
import uvicorn
import sys
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import dotenv
import os

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.factories.config import CONFIGS
from app.service import JudgeRAGService
from app.core.question_recommendations import recommend_questions, run_until_disconnect
from app.security.validate_code import resolve_request_code, validate_code
from app.routers.promptRouter import promptRouter
from app.routers.historyRouter import historyRouter
from app.routers.dailyReportRouter import dailyReportRouter
from app.routers.checkpointRouter import checkpointRouter
from app.routers.documentRouter import documentRouter
from app.routers.figureRouter import figureRouter
from app.routers.cmsRouter import cmsRouter
from app.routers.mesRouter import mesRouter
from app.routers.voiceRouter import voiceRouter

dotenv.load_dotenv("app/.env.back")

from .database import database
from .database.thread_pool_manager import initialize_thread_pools, get_db_thread_pool, get_api_thread_pool

app = FastAPI(title="WAFF Ontology-Driven RAG System")

ASSET_ROOT = ROOT_DIR / "pipeline" / "data"
if ASSET_ROOT.exists():
    app.mount("/assets", StaticFiles(directory=ASSET_ROOT), name="assets")

# Frontend(Next.js)에서 오는 브라우저 요청 허용
app.add_middleware(
    CORSMiddleware,
    # allow_origins=[
    #     "http://localhost:3000",
    #     "http://127.0.0.1:3000",
    # ],
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미리 생성하지 않고 요청 시 초기화
services: dict[str, JudgeRAGService] = {}

def get_service(factory_id: str) -> JudgeRAGService:
    if factory_id not in services:
        cfg = CONFIGS.get(factory_id)
        if not cfg:
            raise HTTPException(status_code=404, detail="해당 공장 설정을 찾을 수 없습니다.")
        services[factory_id] = JudgeRAGService(cfg)
    return services[factory_id]

# nginx 등 리버스 프록시 대응
def get_client_ip_nginx(request: Request) -> str:
    # 프록시 서버 헤더 확인 (확인용 출력 문구)
    # print("--- [모든 헤더 출력 시작] ---")
    # for header_name, header_value in request.headers.items():
    #     print(f"{header_name}: {header_value}")
    # print("--- [모든 헤더 출력 끝] ---")

    forwarded = request.headers.get("X-Forwarded-For")
    # 헤더 있으면 헤더 안 ip 출력
    if forwarded:
        return forwarded.split(",")[0].strip()
    # 프록시 헤더 x 시 기존 ip 출력
    return request.client.host if request.client else "Unknown IP"

class ChatRequest(BaseModel):
    session_id: str
    question: str
    mode: str = "base"          # base | rag | graph
    prompt_id: str = "tech_expert"
    persona_type: str = "operator"
    prompt_no: int | None = None
    restore_memory: bool = False


class RecommendationRequest(BaseModel):
    llm_model: Literal["ollama_config", "vllm_config"] = "ollama_config"
    source: Literal["manual", "ladder", "cms_engineer", "cms_manager"] = "manual"
    session_id: str | None = None
    question: str = Field(default="", max_length=10000)
    answer: str = Field(default="", max_length=50000)


def recommendation_machine_code(request, client_request, service):
    ctx = resolve_request_code(
        request=client_request,
        machines=service.config.machines,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )
    if request.session_id is not None:
        return validate_code(ctx, database.getChatSessionInfo(request.session_id))
    return ctx.request_machine_code


@app.post("/api/recommendations/context")
def recommendation_context(request: RecommendationRequest, client_request: Request):
    service = get_service(request.llm_model)
    machine_code = recommendation_machine_code(request, client_request, service)
    return {"machine_code": machine_code if machine_code != "ALL" else None,
            "machine_name": service.config.machines.get(machine_code, {}).get("machine_name")}


@app.post("/api/recommendations")
async def recommendation_endpoint(request: RecommendationRequest, client_request: Request):
    service = get_service(request.llm_model)
    machine_code = recommendation_machine_code(request, client_request, service)
    if not machine_code or machine_code == "ALL":
        return {"questions": [], "message": "현재 장비가 지정되지 않아 추천질문을 만들 수 없습니다."}
    try:
        asked_questions = []
        conversation = []
        if request.session_id is not None:
            rows = database.getChatMessagesBySession(request.session_id)
            asked_questions = [row[3] for row in rows if row[2] == "user" and row[3]]
            conversation = [{"role": row[2], "content": row[3]} for row in rows
                            if row[2] in ("user", "assistant") and row[3]]
        if not request.question and not request.answer and not asked_questions:
            generation = service.initial_question_cache.get(service, machine_code, source=request.source)
        else:
            generation = recommend_questions(
                service, machine_code, request.question, request.answer, asked_questions=asked_questions,
                conversation=conversation, source=request.source,
            )
        questions = await run_until_disconnect(client_request, generation)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="추천질문을 생성하지 못했습니다. 다시 시도해 주세요.") from exc
    source_label = {"manual": "매뉴얼", "ladder": "래더 정보", "cms_engineer": "CMS 알람 로그", "cms_manager": "CMS 운영 데이터"}[request.source]
    return {"questions": questions, "message": "" if questions else f"매칭된 {source_label}에서 새롭게 이어갈 추천질문을 찾지 못했습니다.",
            "machine_code": machine_code,
            "machine_name": service.config.machines.get(machine_code, {}).get("machine_name", machine_code)}

@app.post("/api/chat/{factory_id}")
# /chat은 HTTP 스트리밍 포맷만 담당한다.
# 프롬프트 조립, LLM 호출, 메모리 저장은 RAGService.ask_stream()에서 처리한다.
async def chat_endpoint(factory_id: str, request: ChatRequest, client_request: Request):
    # 클라이언트 ip 확인
    # user_ip = get_client_ip_nginx(client_request)
    
    service = get_service(factory_id)

    ctx = resolve_request_code(
        request=client_request,
        machines = service.config.machines,
        main_server_ips={os.getenv("MAIN_SERVER_URL", "MSSQL_HOST")},
    )

    session_info = database.getChatSessionInfo(request.session_id)
    effective_machine_code = validate_code(ctx, session_info)
    if request.mode == "cms":
        if request.persona_type not in {"engineer", "manager"}:
            raise HTTPException(status_code=400, detail="CMS 모드는 기술엔지니어 또는 관리자 페르소나에서 사용하세요.")
        if not effective_machine_code or effective_machine_code == "ALL":
            raise HTTPException(status_code=400, detail="CMS 모드는 현재 장비가 지정되어야 합니다.")
    # 프론트에서는 prompt_no만 전달하고, 실제 사용자 프롬프트 원문은 서버에서 DB 기준으로 조회한다.
    user_prompt = None
    if request.prompt_no is not None:
        user_prompt = database.getUserPrompt(request.prompt_no)

    async def event_generator():
        async for event in service.ask_stream(
            session_id=request.session_id,
            question=request.question,
            mode=request.mode,
            prompt_id=request.prompt_id,
            persona_type=request.persona_type,
            user_prompt=user_prompt,
            restore_memory=request.restore_memory,
            effective_machine_code=effective_machine_code
        ):
            if event["type"] == "metadata":
                yield f"METADATA:{json.dumps(event['data'])}\n\n"
            elif event["type"] == "token":
                yield event["data"]

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )

@app.get("/configs")
def list_configs():
    return {
        key: {
            "id":         cfg.id,
            "provider":   cfg.llm.provider,
            "model_name": cfg.llm.model_name,
        }
        for key, cfg in CONFIGS.items()
    }

app.include_router(promptRouter)
app.include_router(historyRouter)
app.include_router(dailyReportRouter)
app.include_router(checkpointRouter)
app.include_router(documentRouter)
app.include_router(figureRouter)
app.include_router(cmsRouter)
app.include_router(mesRouter)
app.include_router(voiceRouter)

if __name__ == "__main__":
    # 스레드 풀 초기화
    initialize_thread_pools()

    try:
        database.get_db_connection()
        uvicorn.run(app, host="0.0.0.0", port=8000)
    finally:
        # 애플리케이션 종료 시 스레드 풀 정리
        get_db_thread_pool().shutdown()
        get_api_thread_pool().shutdown()
