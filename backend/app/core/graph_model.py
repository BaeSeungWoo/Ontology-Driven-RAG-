"""Generate structured graph responses using the chat session's configured model."""
import json

import httpx

from app.core.llm_handler import LLMProvider, LLM_TIMEOUT


async def graph_completion(config, messages, schema):
    llm = config.llm
    definition = schema.model_json_schema()
    if llm.provider == "ollama":
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            response = await client.post(f"{llm.base_url.rstrip('/')}/api/chat", json={
                "model": llm.model_name, "messages": messages, "format": definition,
                "stream": False, "think": False, "options": {"temperature": llm.temperature,
                    "num_ctx": llm.num_ctx, "num_predict": llm.max_tokens},
            })
            response.raise_for_status()
            data = response.json()
            return data["message"]["content"], data.get("done_reason")

    model = LLMProvider.get_model(config)
    if llm.provider == "openai":
        async with model.client as client:
            response = await client.chat.completions.create(
                model=llm.model_name, temperature=llm.temperature, max_tokens=llm.max_tokens,
                response_format={"type": "json_schema", "json_schema": {
                    "name": schema.__name__, "schema": definition}}, messages=messages)
        choice = response.choices[0]
        return choice.message.content or "", choice.finish_reason

    system = messages[0]["content"] + "\nReturn only JSON conforming to: " + json.dumps(definition, ensure_ascii=False)
    content = await model.ainvoke([{"role": "system", "content": system}, *messages[1:]])
    return content.strip().removeprefix("```json").removesuffix("```").strip(), None
