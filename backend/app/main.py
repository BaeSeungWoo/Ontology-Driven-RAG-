# backend/app/main.py

import json
import uvicorn
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import dotenv

from app.factories.config import CONFIGS
from app.service import RAGService
from app.routers.promptRouter import promptRouter
from app.routers.historyRouter import historyRouter
from app.routers.dailyReportRouter import dailyReportRouter
from app.routers.checkpointRouter import checkpointRouter

dotenv.load_dotenv("app/.env.back")

from .database import database
from .database.thread_pool_manager import initialize_thread_pools, get_db_thread_pool, get_api_thread_pool

app = FastAPI(title="WAFF Ontology-Driven RAG System")

ASSET_ROOT = Path(__file__).resolve().parents[2] / "pipeline" / "data"
if ASSET_ROOT.exists():
    app.mount("/assets", StaticFiles(directory=ASSET_ROOT), name="assets")

# Frontend(Next.js)에서 오는 브라우저 요청 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 미리 생성하지 않고 요청 시 초기화
services: dict[str, RAGService] = {}

def get_service(factory_id: str) -> RAGService:
    if factory_id not in services:
        cfg = CONFIGS.get(factory_id)
        if not cfg:
            raise HTTPException(status_code=404, detail="해당 공장 설정을 찾을 수 없습니다.")
        services[factory_id] = RAGService(cfg)
    return services[factory_id]

class ChatRequest(BaseModel):
    session_id: str
    question: str
    mode: str = "base"          # base | rag | graph
    prompt_id: str = "tech_expert"
    prompt_no: int | None = None

@app.post("/chat/{factory_id}")
async def chat_endpoint(factory_id: str, request: ChatRequest):
    service = get_service(factory_id)
    
    user_prompt = None
    if request.prompt_no is not None:
        user_prompt = database.getUserPrompt(request.prompt_no)

    # messages, imgs, tables, chunks = await service.prepare_context(
    #     question = request.question, 
    #     mode = request.mode, 
    #     prompt_id = request.prompt_id, 
    #     user_prompt = user_prompt,
    # )
    messages, imgs, tables, chunks = await service.prepare_ask_context(
        session_id = request.session_id,
        question = request.question, 
        mode = request.mode, 
        prompt_id = request.prompt_id, 
        user_prompt = user_prompt,
    )

    print(f"[DEBUG] messages: {messages}")  # 추가

    async def event_generator():
        # 기능: 토큰 스트리밍 전에 metadata를 먼저 전달한다.
        # 목적: 프론트가 답변 저장 시 chunk/이미지/표 정보를 함께 보존하고 인용근거 패널에 활용하게 한다.
        answer_parts = []

        yield f"METADATA:{json.dumps({'images': imgs, 'tables': tables, 'chunks': chunks})}\n\n"
        async for token in service.llm.astream(messages):
            answer_parts.append(token)
            yield token
        
        answer = "".join(answer_parts)
        service.memory_manager.add_turn(
            request.session_id,
            request.question,
            answer,
        )

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
