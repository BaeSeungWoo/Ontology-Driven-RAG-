# backend/app/main.py

import json
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.factories.config import CONFIGS
from app.service import RAGService


app = FastAPI(title="WAFF Ontology-Driven RAG System")

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

@app.post("/chat/{factory_id}")
async def chat_endpoint(factory_id: str, request: ChatRequest):
    service = get_service(factory_id)

    messages, imgs, chunk_map = await service.prepare_context(
        request.question, request.mode, request.prompt_id
    )

    print(f"[DEBUG] messages: {messages}")  # ← 추가

    async def event_generator():
        yield f"METADATA:{json.dumps({'images': imgs, 'sources': chunk_map})}\n\n"
        async for token in service.llm.astream(messages):
            print(f"[DEBUG] token: {repr(token)}", flush=True)  # ← 추가
            yield token

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

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
