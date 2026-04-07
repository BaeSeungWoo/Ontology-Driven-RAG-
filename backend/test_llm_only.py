# backend/test_llm_only.py

import asyncio
from dotenv import load_dotenv
load_dotenv()

from app.factories.config import CONFIGS
from app.core.llm_handler import LLMProvider

async def test():
    print("=== LLM STREAM TEST ===\n")

    config  = CONFIGS["ollama_config"]
    llm_cfg = config.llm

    messages = [
        {"role": "system", "content": config.prompt.fallback_system_prompt},
        {"role": "user",   "content": "CNC에서 0100 알람이 무엇인가요?"},
    ]

    cls = LLMProvider._MAP.get(llm_cfg.provider)
    llm = cls(llm_cfg)

    token_count = 0
    async for token in llm.astream(messages):
        print(token, end="", flush=True)
        token_count += 1

    print(f"\n\n토큰 수: {token_count}")
    print("=== DONE ===")

asyncio.run(test())