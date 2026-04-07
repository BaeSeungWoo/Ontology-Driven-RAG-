# backend/app/core/prompt_manager.py

import json
from pathlib import Path


TEMPLATE = """\
[페르소나]
{persona}

[이전 대화]
{history}

[참고 정보]
{context}

[질문]
{question}

[답변 지침]
{guide}
답변:"""


class PromptManager:
    """
    prompts/registry.json 에서 페르소나·스타일을 로드하고
    모드(base / rag / graph)에 따라 프롬프트를 조립합니다.
    """

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
        history: str = "",
        context: str = "",
        custom_persona: str = None,     # config.prompt.system_prompt 에서 주입
    ) -> str:
        """
        prompt_id 로 레지스트리에서 설정을 찾아 프롬프트를 조립합니다.
        prompt_id 가 없으면 'tech_expert' 를 기본값으로 사용합니다.
        """
        cfg = self.registry.get(prompt_id) or self.registry["tech_expert"]

        return TEMPLATE.format(
            persona=custom_persona or cfg["persona"],
            history=history or "없음",
            context=context or "없음",
            question=question,
            guide=cfg["guide"],
        )