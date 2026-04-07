# backend/test_stream.py

import asyncio
import sys
import httpx
from dotenv import load_dotenv
load_dotenv()

sys.stdout.reconfigure(encoding="utf-8")

async def test():
    print("=== STREAM TEST ===\n")

    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            "http://localhost:8000/chat/ollama_config",
            json={
                "session_id": "test-001",
                "question":   "CNC에서 0100 알람이 무엇인가요?",
                "prompt_id":  "tech_expert",
            },
        ) as response:
            async for chunk in response.aiter_text():
                if chunk.startswith("METADATA:"):
                    print(f"[META] {chunk}\n[ANSWER] ", end="", flush=True)
                else:
                    print(chunk, end="", flush=True)

    print("\n=== DONE ===")

asyncio.run(test())