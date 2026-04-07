# backend/test_service.py

import asyncio
import sys
import httpx
import json
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

from app.factories.config import CONFIGS
from app.core.llm_handler import OllamaLLM

async def test():
    print("=== OLLAMA 직접 호출 테스트 ===\n")

    config  = CONFIGS["ollama_config"]
    llm_cfg = config.llm

    messages = [
        {"role": "system", "content": config.prompt.fallback_system_prompt},
        {"role": "user",   "content": "CNC에서 0100 알람이 무엇인가요?"},
    ]

    llm = OllamaLLM(llm_cfg)
    prompt = llm._to_prompt(messages)

    thinking_count = 0
    response_count = 0

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{llm_cfg.base_url}/api/generate",
            json={
                "model":  llm_cfg.model_name,
                "prompt": prompt,
                "stream": True,
                "options": {
                    "temperature": llm_cfg.temperature,
                    "num_ctx":     llm_cfg.num_ctx,
                    "num_predict": llm_cfg.max_tokens,
                },
            },
        ) as response:
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)

                thinking = data.get("thinking", "")
                token    = data.get("response", "")

                if thinking:
                    thinking_count += 1
                    if thinking_count == 1:
                        print("[THINKING]", end=" ")
                    print(thinking, end="", flush=True)

                if token:
                    response_count += 1
                    if response_count == 1:
                        print("\n\n[RESPONSE]", end=" ")
                    print(token, end="", flush=True)

    print(f"\n\nthinking 토큰: {thinking_count} / response 토큰: {response_count}")
    print("=== DONE ===")

asyncio.run(test())