# backend/app/core/prompt_manager.py

import json
from pathlib import Path


class PromptManager:
    def __init__(self, registry_path: str = "prompts/registry.json"):
        path = Path(registry_path)
        if not path.exists():
            raise FileNotFoundError(f"프롬프트 레지스트리를 찾을 수 없습니다: {registry_path}")
        with path.open(encoding="utf-8") as f:
            self.registry: dict = json.load(f)

    def build(
        self,
        prompt_id: str,
        question: str,
        history: list = [],           
        context: str = "",
        custom_persona: str = None,
    ) -> list:                        
        cfg = self.registry.get(prompt_id) or self.registry["tech_expert"]

        persona = custom_persona or cfg["persona"]
        guide   = cfg["guide"]       

        # system 메시지 조립
        system_content = persona
        if guide:
            system_content += f"\n\n[답변 지침]\n{guide}"

        # user 메시지 조립
        user_parts = []
        if context:
            user_parts.append(f"[참고 정보]\n{context}")
        user_parts.append(f"[질문]\n{question}")
        user_content = "\n\n".join(user_parts)

        # ✅ messages 리스트 반환 — llm_handler.astream()과 규격 통일
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)      # MemoryManager가 반환한 list 그대로 삽입
        messages.append({"role": "user", "content": user_content})

        return messages