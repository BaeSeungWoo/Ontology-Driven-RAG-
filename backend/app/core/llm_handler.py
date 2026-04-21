# backend/app/core/llm_handler.py

import os
import json
import httpx
from openai import AsyncOpenAI
from google import genai
from google.genai import types

from app.factories.config import LLMConfig

class BaseLLM:
    async def astream(self, messages: list):
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────────
#  OpenAI
# ──────────────────────────────────────────────────────────────────────────────

class OpenAILLM(BaseLLM):
    def __init__(self, cfg: LLMConfig):
        self.client = AsyncOpenAI(
            api_key=cfg.api_key or os.getenv("OPENAI_API_KEY")
        )
        self.model       = cfg.model_name
        self.temperature = cfg.temperature
        self.max_tokens  = cfg.max_tokens

    async def astream(self, messages: list):
        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# ──────────────────────────────────────────────────────────────────────────────
#  Ollama
# ──────────────────────────────────────────────────────────────────────────────

class OllamaLLM(BaseLLM):
    def __init__(self, cfg: LLMConfig):
        # config.base_url 우선, 없으면 환경변수 fallback
        self.base_url    = cfg.base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.model       = cfg.model_name
        self.temperature = cfg.temperature
        self.num_ctx     = cfg.num_ctx
        self.max_tokens  = cfg.max_tokens

    async def astream(self, messages: list):
        prompt = self._to_prompt(messages)

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/generate",
                json={
                    "model":  self.model,
                    "prompt": prompt,
                    "stream": True,
                    "options": {
                        "temperature": self.temperature,
                        "num_ctx":     self.num_ctx,
                        "num_predict": self.max_tokens,
                    },
                    "think": False,
                },
            ) as response:
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)

                    # thinking 모델: 최종 답변은 response 키에 담김
                    # 추론 중에는 thinking 키에 담기므로 무시
                    token = (
                        # data.get("response", "")
                        data.get("response")
                        or data.get("content")
                        or data.get("message", {}).get("content", "")
                    )
                    if token:
                        yield token             

    @staticmethod
    def _to_prompt(messages: list) -> str:
        role_map = {"system": "[SYSTEM]", "user": "[USER]", "assistant": "[ASSISTANT]"}
        prompt = ""
        for m in messages:
            tag = role_map.get(m["role"], "[USER]")
            prompt += f"{tag}\n{m['content']}\n\n"
        prompt += "[ASSISTANT]\n"
        return prompt


# ──────────────────────────────────────────────────────────────────────────────
#  Anthropic
# ──────────────────────────────────────────────────────────────────────────────

class AnthropicLLM(BaseLLM):
    def __init__(self, cfg: LLMConfig):
        self.api_key     = cfg.api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model       = cfg.model_name
        self.temperature = cfg.temperature
        self.max_tokens  = cfg.max_tokens
        self.url         = "https://api.anthropic.com/v1/messages"

    async def astream(self, messages: list):
        # system 메시지 분리 (Anthropic API 규격)
        system_prompt = next(
            (m["content"] for m in messages if m["role"] == "system"), ""
        )
        user_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages if m["role"] != "system"
        ]

        payload = {
            "model":       self.model,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
            "stream":      True,
            "messages":    user_messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key":         self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }

        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", self.url, headers=headers, json=payload) as response:
                async for line in response.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    raw = line.removeprefix("data:").strip()
                    if raw == "[DONE]":
                        break
                    try:
                        event = json.loads(raw)
                        if event.get("type") == "content_block_delta":
                            yield event["delta"].get("text", "")
                    except json.JSONDecodeError:
                        continue


# ──────────────────────────────────────────────────────────────────────────────
#  Google Gemini
# ──────────────────────────────────────────────────────────────────────────────

class GoogleLLM(BaseLLM):
    def __init__(self, cfg: LLMConfig):
        self.client      = genai.Client(api_key=cfg.api_key or os.getenv("GOOGLE_API_KEY"))
        self.model       = cfg.model_name
        self.temperature = cfg.temperature
        self.max_tokens  = cfg.max_tokens

    async def astream(self, messages: list):
        system_prompt = next(
            (m["content"] for m in messages if m["role"] == "system"), ""
        )

        # system 제외한 나머지를 google-genai Content 형식으로 변환
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages if m["role"] != "system"
        ]

        config = types.GenerateContentConfig(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens,
            system_instruction=system_prompt or None,
        )

        # 동기 스트리밍을 비동기로 래핑
        import asyncio
        loop = asyncio.get_event_loop()
        stream = await loop.run_in_executor(
            None,
            lambda: self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
        )

        for chunk in stream:
            if chunk.text:
                yield chunk.text

# ──────────────────────────────────────────────────────────────────────────────
#  Provider Factory
# ──────────────────────────────────────────────────────────────────────────────

class LLMProvider:
    _MAP = {
        "openai":    OpenAILLM,
        "ollama":    OllamaLLM,
        "anthropic": AnthropicLLM,
        "google":    GoogleLLM,
    }

    @staticmethod
    def get_model(config) -> BaseLLM:
        cls = LLMProvider._MAP.get(config.llm.provider)
        if not cls:
            raise ValueError(
                f"[{config.id}] 지원하지 않는 LLM 공급자: {config.llm.provider}"
            )
        return cls(config.llm)      # LLMConfig 전체를 전달
    
if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()

    from app.factories.config import CONFIGS

    async def test():
        print("=== TEST START ===")

        config  = CONFIGS["ollama_config"]
        llm_cfg = config.llm

        messages = [
            {"role": "system", "content": config.prompt.fallback_system_prompt},
            {"role": "user",   "content": "CNC에서 0100 알람이 무엇인가요?"},
        ]

        cls = LLMProvider._MAP.get(llm_cfg.provider)
        llm = cls(llm_cfg)

        async for token in llm.astream(messages):
            print(token, end="", flush=True)

        print("\n=== TEST DONE ===")

    asyncio.run(test())