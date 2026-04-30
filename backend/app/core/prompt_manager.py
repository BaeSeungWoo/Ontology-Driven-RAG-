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
        prompt_id: str,                     # registry.json - ex) "tech_expert"
        question: str,                      # 사용자가 채팅창에 입력한 질문
        history: list | None = None,                 # Memory_manager가 넘겨주는 이전 대화
        context: str = "",                  # RAG/Graph 검색으로 가져온 참고 정보
        user_prompt: str | None = None,     # DB에서 가져온 사용자 정의 프롬프트
        mode: str = "base",                 # base | rag | graph
        system_override: str | None = None, # system prompt를 덮어써야할 때만 사용
    ) -> list:  
        # ======================================================                      
        # system message:
        #   registry.json 기반. 모델의 역할, 규칙, 출력 제약
        #   ㄴ persona
        #   ㄴ response_policy
        #   ㄴ rag_policy
        #   ㄴ citation_policy
        #   ㄴ citation_examples
        #   ㄴ output_format

        # history:
        #   MemoryManager에서 받은 이전 대화

        # user message:
        #   context
        #   DB user_prompt 
        #   question
        # ======================================================

        cfg = self.registry.get(prompt_id) or self.registry["tech_expert"]

        # 방어코드 예시
        # if cfg.get("type") != "chat_rag":
        #     cfg = self.registry["tech_expert"]

        persona = system_override or cfg.get("persona", "")
        response_policy = cfg.get("response_policy", [])
        rag_policy = cfg.get("rag_policy", [])
        citation_policy = cfg.get("citation_policy", [])
        citation_examples = cfg.get("citation_examples", {})
        output_format = cfg.get("output_format", {})

        # system 메시지 조립
        system_sections = []

        if persona:
            system_sections.append(persona)

        if response_policy:
            system_sections.append(
                "[응답 규칙]\n" + "\n".join(f"- {rule}" for rule in response_policy)
            )

        if rag_policy and mode != "base":
            system_sections.append(
                "[RAG 규칙]\n" + "\n".join(f"- {rule}" for rule in rag_policy)
            )

        # base일 경우에는 chunk가 없으니 context가 있는 경우에만
        if citation_policy and context:
            system_sections.append(
                "[인용 규칙]\n" + "\n".join(f"- {rule}" for rule in citation_policy)
            )

        bad_examples = citation_examples.get("bad", [])
        good_examples = citation_examples.get("good", [])

        if context and (bad_examples or good_examples):
            example_text = []

            if bad_examples:
                example_text.append(
                    "잘못된 예:\n" + "\n".join(f"- {item}" for item in bad_examples)
                )

            if good_examples:
                example_text.append(
                    "좋은 예:\n" + "\n".join(f"- {item}" for item in good_examples)
                )

            system_sections.append("[인용 예시]\n" + "\n\n".join(example_text))

        default_format = output_format.get("default", [])

        if default_format:
            system_sections.append(
                "[출력 형식]\n" + "\n".join(f"- {item}" for item in default_format)
            )

        system_content = "\n\n".join(system_sections)

        # history 
        history = history or []

        # user 메시지 조립
        user_parts = []

        if context:
            user_parts.append(f"[참고 정보]\n{context}")

        if user_prompt:
            user_parts.append(f"[사용자 프롬프트]\n{user_prompt}")

        user_parts.append(f"[질문]\n{question}")

        user_content = "\n\n".join(user_parts)

        # ✅ messages 리스트 반환 — llm_handler.astream()과 규격 통일
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)      # MemoryManager가 반환한 list 그대로 삽입
        messages.append({"role": "user", "content": user_content})

        return messages