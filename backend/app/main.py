# backend/app/main.py

import json
import uvicorn

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.factories.config import CONFIGS
from app.service import RAGService


app = FastAPI(title="WAFF Ontology-Driven RAG System")

# 서비스 인스턴스를 미리 생성하여 캐싱
services = {fid: RAGService(cfg) for fid, cfg in CONFIGS.items()}


class ChatRequest(BaseModel):
    session_id: str
    question: str
    mode: str = "rag"          # base | rag | graph
    prompt_id: str = "tech_expert"


@app.post("/chat/{factory_id}")
async def chat_endpoint(factory_id: str, request: ChatRequest):
    # 1. 공장 설정 확인
    service = services.get(factory_id)
    if not service:
        raise HTTPException(status_code=404, detail="해당 공장 설정을 찾을 수 없습니다.")

    # 2. 검색 및 컨텍스트 준비 (비스트리밍)
    full_prompt, imgs, chunk_map = await service.prepare_context(
        request.question, request.mode
    )

    # 3. 스트리밍 응답 생성
    async def event_generator():
        # 출처 · 이미지 메타데이터를 먼저 전송
        yield f"METADATA:{json.dumps({'images': imgs, 'sources': chunk_map})}\n\n"

        # LLM 토큰 스트리밍
        async for token in service.llm.astream(full_prompt):
            yield token.content

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)