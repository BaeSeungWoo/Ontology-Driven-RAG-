# tests/unit/test_prompt_manager.py

import pytest
from app.core.prompt_manager import PromptManager


class TestPromptManagerInit:
    def test_loads_registry_from_json(self, registry_path):
        pm = PromptManager(registry_path=registry_path)
        assert "tech_expert" in pm.registry
        assert "maintenance_expert" in pm.registry

    def test_raises_if_file_not_found(self, tmp_path):
        nonexistent = str(tmp_path / "does_not_exist.json")
        with pytest.raises(FileNotFoundError) as exc_info:
            PromptManager(registry_path=nonexistent)
        assert "does_not_exist.json" in str(exc_info.value)


class TestPromptManagerBuild:
    @pytest.fixture
    def pm(self, registry_path):
        return PromptManager(registry_path=registry_path)

    def test_build_fills_all_template_fields(self, pm):
        result = pm.build(
            prompt_id="tech_expert",
            question="테스트 질문",
            history="이전 대화",
            context="참고 문서",
        )
        assert "이전 대화" in result
        assert "참고 문서" in result
        assert "테스트 질문" in result
        assert "당신은 기술 전문가입니다." in result

    def test_build_uses_none_history_placeholder(self, pm):
        result = pm.build(prompt_id="tech_expert", question="Q")
        assert "없음" in result

    def test_build_uses_none_context_placeholder(self, pm):
        result = pm.build(prompt_id="tech_expert", question="Q")
        # context 없음 → "없음"이 포함되어야 함
        assert "없음" in result

    def test_build_uses_custom_persona_over_registry(self, pm):
        result = pm.build(
            prompt_id="tech_expert",
            question="Q",
            custom_persona="커스텀 페르소나",
        )
        assert "커스텀 페르소나" in result
        assert "당신은 기술 전문가입니다." not in result

    def test_build_falls_back_to_tech_expert_for_unknown_id(self, pm):
        result = pm.build(prompt_id="nonexistent_id", question="Q")
        assert "당신은 기술 전문가입니다." in result

    def test_build_output_contains_template_structure(self, pm):
        result = pm.build(prompt_id="tech_expert", question="Q")
        assert "[페르소나]" in result
        assert "[이전 대화]" in result
        assert "[참고 정보]" in result
        assert "[질문]" in result
        assert "[답변 지침]" in result

    def test_build_uses_registry_persona_when_no_custom(self, pm):
        result = pm.build(prompt_id="maintenance_expert", question="Q", custom_persona=None)
        assert "당신은 설비 유지보수 전문가입니다." in result

    def test_build_uses_registry_guide(self, pm):
        result = pm.build(prompt_id="tech_expert", question="Q")
        assert "정확하고 간결하게 답변하세요." in result

    def test_build_maintenance_expert_guide(self, pm):
        result = pm.build(prompt_id="maintenance_expert", question="Q")
        assert "안전 절차를 우선적으로 안내하세요." in result
