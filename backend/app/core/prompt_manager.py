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

    # DB 사용자 프롬프트는 system prompt가 아니라 user message의 하위 지시로 삽입한다.
    # 역할/안전/인용 규칙은 registry.json의 system prompt가 우선한다.
    def build(
        self,
        prompt_id: str,                     # registry.json - ex) "tech_expert"
        question: str,                      # 사용자가 채팅창에 입력한 질문
        m_info: dict | None = None,         # 장비정보
        history: list | None = None,        # Memory_manager가 넘겨주는 이전 대화
        context: str = "",                  # RAG/Graph 검색으로 가져온 참고 정보
        user_prompt: str | None = None,     # DB에서 가져온 사용자 정의 프롬프트
        mode: str = "base",                 # base | rag | graph
        persona_type: str = "operator",
        intent_type: str = "troubleshooting",
        system_override: str | None = None, # system prompt를 덮어써야할 때만 사용
    ) -> list:  
        # ======================================================                      
        # system message:
        #   registry.json 기반. 모델의 역할, 규칙, 출력 제약
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

        m_info = m_info or {}
        base_persona_raw = system_override or cfg.get("base_persona", cfg.get("persona", ""))
        if isinstance(base_persona_raw, list):
            base_persona = "\n".join(base_persona_raw)
        else:
            base_persona = base_persona_raw
        domain_notation_policy = cfg.get("domain_notation_policy", [])
        persona_overlays = cfg.get("persona_overlays", {})
        persona_overlay = ""
        if isinstance(persona_overlays, dict) and not system_override:
            persona_overlay_raw = persona_overlays.get(persona_type) or persona_overlays.get("operator", "")
            if isinstance(persona_overlay_raw, list):
                persona_overlay = "\n".join(persona_overlay_raw)
            else:
                persona_overlay = persona_overlay_raw
        intent_policies = cfg.get("intent_policies", {})
        intent_policy = ""
        if isinstance(intent_policies, dict):
            intent_policy_raw = intent_policies.get(intent_type) or intent_policies.get("troubleshooting", "")
            if isinstance(intent_policy_raw, list):
                intent_policy = "\n".join(intent_policy_raw)
            else:
                intent_policy = intent_policy_raw
        response_policy = cfg.get("response_policy", [])
        rag_policy = cfg.get("rag_policy", [])
        citation_policy = cfg.get("citation_policy", [])
        citation_examples = cfg.get("citation_examples", {})
        output_format = cfg.get("output_format", {})

        # system 메시지 조립
        system_sections = []

        # 장비 정보 등록 예시
        # [장비 정보]
        # - 장비명: LCV-6700 #1
        # - IP: 192.168.1.10
        # - 제조사: SMEC
        # - 컨트롤러: 화낙
        # - 버전: 0i-MF
        if m_info:
            machine_lines = [                
                "장비명: " + m_info.get('machine_name'),
                "IP: " +  m_info.get('machine_ip'),
                "제조사: " +  m_info.get('machine_maker'),
                "컨트롤러: " +  m_info.get('machine_controller'),
                "버전: " +  m_info.get('machine_ver'),
            ]

            system_sections.append("[장비 정보]\n" + "\n".join(machine_lines))

        if base_persona:
            system_sections.append(base_persona)

        if domain_notation_policy:
            system_sections.append(
                "[도메인 표기 규약]\n" + "\n".join(f"- {rule}" for rule in domain_notation_policy)
            )

        if persona_overlay:
            system_sections.append("[PERSONA]\n" + persona_overlay)

        if intent_policy:
            system_sections.append("[INTENT]\n" + intent_policy)

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

        # print(f"system_content : {system_content}")

        # ✅ messages 리스트 반환 — llm_handler.astream()과 규격 통일
        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)      # MemoryManager가 반환한 list 그대로 삽입
        messages.append({"role": "user", "content": user_content})

        return messages

    # summary 타입 프롬프트를 사용해 대화 메모리 압축용 messages를 조립한다.
    def build_summary(
        self,
        prompt_id: str = "memory_summary",
        history_text: str = "",
    ) -> list:
        cfg = self.registry.get(prompt_id) or self.registry["memory_summary"]

        persona = cfg.get("persona", "")
        summary_policy = cfg.get("summary_policy", [])
        output_format = cfg.get("output_format", {})

        system_sections = []

        if persona:
            system_sections.append(persona)

        if summary_policy:
            system_sections.append(
                "[요약 규칙]\n" + "\n".join(f"- {rule}" for rule in summary_policy)
            )

        default_format = output_format.get("default", [])

        if default_format:
            system_sections.append(
                "[출력 형식]\n" + "\n".join(f"- {item}" for item in default_format)
            )

        system_content = "\n\n".join(system_sections)
        user_content = f"[압축 대상 대화]\n{history_text}"

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    # kg 생성 시 llm에 넘겨 줄 프롬프트 생성
    def build_kg_prompt(self, text: str, prompt_id: str = "extract_triple") -> list:
        cfg = self.registry.get(prompt_id) or self.registry["extract_triple"]

        def _format_fewshot() -> str:
            parts = []
            for ex in FEWSHOT:
                parts.append(
                    "Passage:\n" + ex["passage"] + "\n"
                    "Triples:\n" + json.dumps(ex["triples"], ensure_ascii=False)
                )
            return "\n\n".join(parts)
        system_content = cfg.get("persona", "")

        FEWSHOT = [
            {
                "passage": (
                    "The Transformer is the first transduction model relying entirely on "
                    "self-attention to compute representations of its input and output "
                    "without using sequence-aligned RNNs or convolution."
                ),
                "triples": [
                    ["Transformer", "is", "first transduction model relying entirely on self-attention"],
                    ["Transformer", "computes representations of", "its input and output"],
                    ["Transformer", "does not use", "sequence-aligned RNNs"],
                    ["Transformer", "does not use", "convolution"],
                ],
            },
            {
                "passage": (
                    "System alarm 195 indicates an embedded software system error and is "
                    "logged in the alarm history."
                ),
                "triples": [
                    ["system alarm 195", "indicates", "embedded software system error"],
                    ["system alarm 195", "is logged in", "alarm history"],
                ],
            },
            {
                "passage": (
                    "The Adam optimizer was used with beta1 = 0.9 and beta2 = 0.98."
                ),
                "triples": [
                    ["Adam optimizer", "was used with beta1", "0.9"],
                    ["Adam optimizer", "was used with beta2", "0.98"],
                ],
            },
        ]

        PROMPT_TEMPLATE = (
            "{fewshot}\n\n"
            "Passage:\n{passage}\n"
            "Triples (JSON array of [s, p, o] arrays, no commentary):\n"
        )

        user_content = PROMPT_TEMPLATE.format(fewshot=_format_fewshot(), passage=text.strip())

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    # judge 판단용 프롬프트 세팅
    def build_judge_prompt(self, text: str, graph_out: dict, doc_out: dict, mm_out: dict, prompt_id: str = "judge") -> list:
        cfg = self.registry.get(prompt_id) or self.registry["judge"]
        
        system_content = cfg.get("persona", "")

        def _format_sections(secs: list[str], limit: int = 5) -> str:
            if not secs:
                return "(none)"
            short = secs[:limit]
            return " | ".join(short)


        def _format_triples(triples: list[tuple[str, str, str]], limit: int = 5) -> str:
            if not triples:
                return "(none)"
            return " | ".join(f"({s},{p},{o})" for s, p, o in triples[:limit])

        TRIPLE_TEMPLATE = """Question: {question}
            [Candidate A — KG-grounded Graph RAG]
            Answer: {a_answer}
            KG triples used: {a_triples}
            Sections: {a_sections}

            [Candidate B — vector Doc RAG]
            Answer: {b_answer}
            Sections: {b_sections}

            [Candidate C — multimodal (Colpali) RAG]
            Answer: {c_answer}
            Related sections: {c_sections}

            Output STRICT JSON: {{"choice": "A" | "B" | "C" | "SYNTH", "reason": "<short>", "final_answer": "<full answer>"}}
        """
        user_content = TRIPLE_TEMPLATE.format(
            question=text,
            a_answer=graph_out.get("answer", "").strip(),
            a_triples=_format_triples(graph_out.get("triples") or []),
            a_sections=_format_sections(graph_out.get("section_titles") or []),
            b_answer=doc_out.get("answer", "").strip(),
            b_sections=_format_sections(doc_out.get("section_titles") or []),
            c_answer=mm_out.get("answer", "").strip(),
            c_sections=_format_sections(mm_out.get("section_titles") or []),
        )

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def build_multimodal(
        self,
        question: str,
        context: str,
        history: list | None = None,
    ) -> list:
        system_content = (
            "매뉴얼 전문가입니다. 회수된 도면/이미지의 인접 텍스트로 답하세요. "
            "관련 어드레스/심볼 우선. 'Sources:' 블록 금지."
        )

        history = history or []
        user_content = (
            f"회수된 도면 + 인접 텍스트:\n{context or '(이미지만 회수됨)'}\n\n"
            f"질문: {question}\n\n답변:"
        )

        messages = [{"role": "system", "content": system_content}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_content})
        return messages