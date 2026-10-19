"""OpenAI-compatible chat client used by the QA engine (text + vision).

Endpoint: env VLLM_API_BASE (default http://127.0.0.1:8001/v1), model: env VLLM_API_MODEL.
Works with llama.cpp (Gemma-4 + --mmproj), vLLM, or the OpenAI API (set OPENAI_API_KEY).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request


def get_logger(name: str = "rag") -> logging.Logger:
    log = logging.getLogger(name)
    if not log.handlers:
        log.setLevel(logging.INFO)
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
        log.addHandler(h)
        log.propagate = False
    return log


log = get_logger("llm")


class LLM:
    RETRY_STATUS = (500, 502, 503, 504, 529)   # llama.cpp returns 5xx when slots are crowded

    def __init__(self, model_name: str, backend: str = "vllm_api",
                 api_base: str = "http://127.0.0.1:8001/v1", api_model: str | None = None, **_):
        self.api_base = api_base.rstrip("/")
        self.api_model = self.model_name = api_model or model_name
        self.is_openai = "api.openai.com" in self.api_base
        self.key = os.getenv("OPENAI_API_KEY") or "x"
        self.last_finish_reason = None
        self.last_usage: dict = {}

    def _extra(self) -> dict:
        # Gemma-4 under llama.cpp --jinja thinks by default and returns an empty `content`.
        from runtime_support import chat_extra
        return chat_extra()

    def _post(self, payload: dict, timeout: int = 300, attempts: int = 1) -> dict:
        from runtime_support import bounded_messages
        cap = int(os.getenv("GRAPHRAG_MAX_TOKENS", "3000"))
        payload["max_tokens"] = min(payload.get("max_tokens", cap), cap)
        payload["messages"] = bounded_messages(payload["messages"], payload["max_tokens"])
        req = urllib.request.Request(
            f"{self.api_base}/chat/completions", data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        last = None
        for i in range(attempts):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code not in self.RETRY_STATUS:   # 4xx: the request itself is wrong
                    raise
                last = e
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
            if i < attempts - 1:
                log.warning(f"server call failed ({last}); retry {i + 2}/{attempts} in {5 * 2 ** i}s")
                time.sleep(5 * 2 ** i)
        raise last

    def chat(self, system: str, user: str, max_new_tokens: int = 512, temperature: float = 0.0,
             stop_strings: list[str] | None = None, response_format: dict | None = None,
             include_answer_context: bool = True) -> str:
        if include_answer_context and max_new_tokens >= 1000:
            system += os.getenv("GRAPHRAG_ANSWER_CONTEXT", "")
        payload = {"model": self.api_model, "temperature": temperature, "max_tokens": max_new_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                   **self._extra(), **({"stop": stop_strings} if stop_strings else {})}
        if response_format is not None:
            payload['response_format'] = response_format
        ch = self._post(payload)["choices"][0]
        self.last_finish_reason = ch.get("finish_reason")
        if self.last_finish_reason == "length":
            log.warning(f"generation hit max_tokens={max_new_tokens}; answer may be cut")
        return ch["message"]["content"].strip()

    def chat_vision(self, system: str, user: str, image_paths, max_new_tokens: int = 768,
                    temperature: float = 0.0) -> str:
        if int(os.getenv("GRAPHRAG_MAX_IMAGES", "0")) == 1 and len(image_paths) > 1:
            # Keep every view when a server accepts only one image. A labelled
            # contact sheet preserves their ordering and full crop resolution.
            import io
            from PIL import Image, ImageDraw
            images = []
            for path in image_paths:
                with Image.open(path) as source:
                    images.append(source.convert("RGB"))
            sheet = Image.new("RGB", (sum(im.width for im in images), max(im.height for im in images) + 32), "white")
            draw, x = ImageDraw.Draw(sheet), 0
            for n, im in enumerate(images, 1):
                draw.text((x + 4, 8), f"Image {n}", fill="black")
                sheet.paste(im, (x, 32))
                x += im.width
            buffer = io.BytesIO()
            sheet.save(buffer, format="PNG")
            urls = ["data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()]
            user += "\nThe views are combined left to right in one image, labelled Image 1, Image 2, etc."
        else:
            urls = []
            for path in image_paths:
                with open(path, "rb") as image_file:
                    urls.append("data:image/png;base64," + base64.b64encode(image_file.read()).decode())
        content = [{"type": "text", "text": user}] + [
            {"type": "image_url", "image_url": {"url": url}} for url in urls]
        payload = {"model": self.api_model, "temperature": temperature, "max_tokens": max_new_tokens,
                   "messages": [{"role": "system", "content": system}, {"role": "user", "content": content}],
                   **self._extra()}
        return self._post(payload, timeout=600)["choices"][0]["message"]["content"].strip()
