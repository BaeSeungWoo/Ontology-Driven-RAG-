import json

from fastapi.responses import StreamingResponse


def explanation_response(llm=None, messages=None, *, sources=None, answer=None, error_message=""):
    def frame(event):
        return json.dumps(event, ensure_ascii=False) + "\n"

    async def generate():
        try:
            yield frame({"sources": sources or []})
            has_text = False
            if answer is not None:
                has_text = bool(answer.strip())
                yield frame({"delta": answer})
            else:
                async for token in llm.astream(messages):
                    has_text = has_text or bool(token.strip())
                    yield frame({"delta": token})
            if not has_text:
                yield frame({"error": error_message})
                return
            yield frame({"done": True})
        except Exception:
            yield frame({"error": error_message})
        finally:
            if llm is not None:
                await llm.client.close()

    return StreamingResponse(generate(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })
