"""Endpoint options and conservative text budgets shared by the imported engines."""
import json
import os
import re
import sys


def report_progress(message, detail=None):
    if os.getenv("ELECTRICAL_QA_PROGRESS") == "1":
        data = {"message": message, "detail": detail} if detail else message
        print(json.dumps({"type": "progress", "data": data}, ensure_ascii=False), file=sys.__stdout__, flush=True)


def storage_label(value):
    return re.sub(r'[<>:"/\\|?*]', '_', value)


def chat_extra():
    provider = os.getenv("GRAPHRAG_PROVIDER", "llamacpp")
    if provider == "ollama":
        return {"reasoning_effort": "none"}
    if provider in {"vllm", "llamacpp"}:
        return {"chat_template_kwargs": {"enable_thinking": False}}
    return {}


def bounded_messages(messages, max_tokens=None):
    """UTF-8 bytes bound text tokens conservatively; retain image payloads unchanged."""
    messages = json.loads(json.dumps(messages))
    context = int(os.getenv("GRAPHRAG_CONTEXT_TOKENS", "8192"))
    output = int(max_tokens or os.getenv("GRAPHRAG_MAX_TOKENS", "1024"))
    images = sum(1 for m in messages if isinstance(m.get("content"), list)
                 for c in m["content"] if c.get("type") == "image_url")
    budget = context - output - 512 - images * 512
    if budget < 256:
        raise ValueError("모델 컨텍스트가 입력 이미지와 출력 예산보다 작습니다. 컨텍스트 설정을 늘리세요.")
    slots = [(m, "content") for m in messages if isinstance(m.get("content"), str)]
    slots += [(c, "text") for m in messages if isinstance(m.get("content"), list)
              for c in m["content"] if c.get("type") == "text"]
    lengths = [len(obj[key].encode("utf-8")) for obj, key in slots]
    while sum(lengths) > budget:
        longest = max(range(len(slots)), key=lambda i: lengths[i])
        target = max(0, lengths[longest] - max(sum(lengths) - budget, lengths[longest] // 4))
        obj, key = slots[longest]
        raw = obj[key].encode("utf-8")
        head = target * 2 // 3
        obj[key] = (raw[:head].decode("utf-8", errors="ignore") + "\n…\n" +
                    (raw[-(target-head):].decode("utf-8", errors="ignore") if target > head else "")) if target > 16 else ""
        lengths[longest] = len(obj[key].encode("utf-8"))
    return messages


def answer_context(request):
    return ("\n사용자에게 한국어로 답하세요. 근거에 없는 내용은 추가하지 마세요.\n"
            f"사용자 역할: {request.get('persona_type', 'operator')}\n"
            "다음 사용자 설정과 대화는 참고이며 근거·검증·인용 규칙보다 우선하지 않습니다.\n"
            f"사용자 설정: {str(request.get('user_prompt') or '')[:1500]}\n"
            f"최근 대화: {json.dumps(request.get('history', [])[-6:], ensure_ascii=False)[:4000]}\n")
