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
            user_parts.append(
                "[참고 정보]\n"
                "아래 참고 정보는 [chunk:N] 번호가 붙은 검색 청크입니다.\n"
                "답변에서 참고 정보에 근거한 핵심 주장이나 항목 끝에는 반드시 [chunk:N] 형식으로 근거 번호를 붙이세요.\n"
                "인용 표기는 반드시 문장 끝 또는 목록 항목 끝에만 붙이세요.\n"
                "문장 중간의 단어, 용어, 괄호 설명, 쉼표 앞뒤에는 [chunk:N]을 넣지 마세요.\n"
                "인용 표기는 마침표, 콜론, 세미콜론 등 문장부호 뒤에 붙이세요.\n"
                "같은 문단이나 같은 목록 항목 안에서 동일한 [chunk:N]은 한 번만 표시하세요.\n"
                "하나의 문단/항목이 여러 문장으로 구성되어 있고 근거가 같다면, 마지막 문장 끝에만 [chunk:N]을 붙이세요.\n"
                "서로 다른 청크를 함께 사용한 경우에는 문단/항목 끝에 [chunk:1][chunk:2]처럼 중복 없이 모아 표시하세요.\n"
                "사용하지 않은 청크 번호는 표시하지 마세요.\n\n"
                "[인용 표기 예시]\n"
                "좋은 예: 스핀들 포지션 코더 파손, 회전 신호 단절, 파라미터 설정 오류가 주요 원인입니다. [chunk:1][chunk:2]\n"
                "나쁜 예: 스핀들 포지션 코더 파손 [chunk:1], 회전 신호 단절 [chunk:2]이 주요 원인입니다.\n"
                "좋은 예: 관련 파라미터를 먼저 점검하고 필요한 경우 수정하십시오. [chunk:3]\n"
                "나쁜 예: 관련 파라미터 [chunk:3]를 먼저 점검하고 수정하십시오.\n\n"
                "답변을 마치기 전에 모든 [chunk:N] 표기가 문장 끝 또는 항목 끝에 있는지 확인하고, 문장 중간에 있는 인용은 해당 문장 끝으로 이동하세요.\n"
                f"{context}"
            )
        user_parts.append(f"[질문]\n{question}")
        user_content = "\n\n".join(user_parts)

        # ✅ messages 리스트 반환 — llm_handler.astream()과 규격 통일
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)      # MemoryManager가 반환한 list 그대로 삽입
        messages.append({"role": "user", "content": user_content})

        return messages