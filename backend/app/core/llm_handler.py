# backend/app/core/llm_handler.py

import os
import httpx
from openai import AsyncOpenAI

class BaseLLM:
    async def astream(self, messages):
        raise NotImplementedError

# =========================
# ✅ OpenAI
# =========================
class OpenAILLM(BaseLLM):
    def __init__(self, model):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.model = model

    async def astream(self, messages):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=0
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# =========================
# ✅ Ollama (로컬 LLM)
# =========================
class OllamaLLM(BaseLLM):
    def __init__(self, model, base_url):
        self.model = model
        self.base_url = base_url

    async def astream(self, messages):
        prompt = self._convert_messages_to_prompt(messages)

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": 0,
                        "num_ctx": 8192
                    }
                }
            ) as response:
                async for line in response.aiter_lines():
                    if line:
                        import json
                        data = json.loads(line)
                        if "response" in data:
                            yield data["response"]

    def _convert_messages_to_prompt(self, messages):
        prompt = ""
        for m in messages:
            role = m["role"]
            content = m["content"]

            if role == "system":
                prompt += f"[SYSTEM]\n{content}\n\n"
            elif role == "user":
                prompt += f"[USER]\n{content}\n\n"
            elif role == "assistant":
                prompt += f"[ASSISTANT]\n{content}\n\n"

        prompt += "[ASSISTANT]\n"
        return prompt


# =========================
# ✅ Anthropic (Claude)
# =========================
class AnthropicLLM(BaseLLM):
    def __init__(self, model):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.url = "https://api.anthropic.com/v1/messages"

    async def astream(self, messages):
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        payload = {
            "model": self.model,
            "max_tokens": 1024,
            "temperature": 0,
            "messages": [
                {"role": m["role"], "content": m["content"]}
                for m in messages if m["role"] != "system"
            ]
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                self.url,
                headers=headers,
                json=payload
            ) as response:
                async for line in response.aiter_lines():
                    if line and "delta" in line:
                        yield line


# =========================
# ✅ Provider Factory
# =========================
class LLMProvider:
    @staticmethod
    def get_model(config):
        provider = config.llm.provider

        if provider == "openai":
            return OpenAILLM(config.llm.model_name)

        elif provider == "ollama":
            return OllamaLLM(
                model=config.llm.model_name,
                base_url=config.llm.base_url
            )

        elif provider == "anthropic":
            return AnthropicLLM(config.llm.model_name)

        raise ValueError(
            f"[{config.id}] 지원하지 않는 LLM 공급자: {provider}"
        )
    
if __name__ == "__main__":
    import asyncio
    from types import SimpleNamespace

    async def test():
        print("=== LLMProvider TEST START ===")

        # 👉 테스트용 config
        config = SimpleNamespace(
            id="test",
            llm=SimpleNamespace(
                provider="ollama",   # 👉 "ollama"로 바꿔도 테스트 가능
                model_name="gpt-oss:20b",
                base_url="http://192.168.1.179:11434"
            )
        )

        llm = LLMProvider.get_model(config)

        messages = [
            {"role": "system", "content": "당신은 친절한 기술 전문가입니다. 질문에 대해 간결하고 명확하게 답변하세요."},
            {"role": "user", "content": "CNC에서 0100 알람이 무엇인가요?"}
        ]

        async for token in llm.astream(messages):
            print(token, end="", flush=True)

        print("\n=== TEST DONE ===")

    asyncio.run(test())