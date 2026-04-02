# tests/unit/test_memory_manager.py

import pytest
from app.core.memory_manger import MemoryManager


class TestMemoryManagerBasic:
    def test_get_history_empty_session_returns_empty_string(self):
        mm = MemoryManager()
        result = mm.get_history("new_session")
        assert result == ""

    def test_save_creates_session_entry(self):
        mm = MemoryManager()
        mm.save("s1", "질문", "답변")
        assert "s1" in mm.sessions

    def test_get_history_after_save_contains_question_and_answer(self):
        mm = MemoryManager()
        mm.save("s1", "무엇인가요?", "이것입니다.")
        history = mm.get_history("s1")
        assert "무엇인가요?" in history
        assert "이것입니다." in history

    def test_get_history_labels_human_and_ai(self):
        mm = MemoryManager()
        mm.save("s1", "Q", "A")
        history = mm.get_history("s1")
        assert "사용자" in history
        assert "AI" in history

    def test_save_multiple_pairs_and_get_history(self):
        mm = MemoryManager()
        for i in range(3):
            mm.save("s1", f"Q{i}", f"A{i}")
        history = mm.get_history("s1")
        assert "Q0" in history
        assert "Q2" in history
        assert "A2" in history


class TestMemoryManagerWindow:
    def test_window_eviction_respects_k(self):
        mm = MemoryManager(k=2)
        for i in range(3):
            mm.save("s1", f"Q{i}", f"A{i}")
        history = mm.get_history("s1")
        # k=2이므로 Q0/A0는 밀려나야 함
        assert "Q0" not in history
        assert "Q1" in history
        assert "Q2" in history

    def test_default_k_is_5(self):
        mm = MemoryManager()
        assert mm.k == 5


class TestMemoryManagerClear:
    def test_clear_removes_session(self):
        mm = MemoryManager()
        mm.save("s1", "Q", "A")
        mm.clear("s1")
        assert "s1" not in mm.sessions

    def test_get_history_after_clear_returns_empty(self):
        mm = MemoryManager()
        mm.save("s1", "Q", "A")
        mm.clear("s1")
        assert mm.get_history("s1") == ""

    def test_clear_nonexistent_session_does_not_raise(self):
        mm = MemoryManager()
        mm.clear("does_not_exist")  # 예외 없이 통과해야 함


class TestMemoryManagerIsolation:
    def test_multiple_sessions_are_independent(self):
        mm = MemoryManager()
        mm.save("s1", "Q1", "A1")
        mm.save("s2", "Q2", "A2")
        history_s1 = mm.get_history("s1")
        history_s2 = mm.get_history("s2")
        assert "Q1" in history_s1
        assert "Q2" not in history_s1
        assert "Q2" in history_s2
        assert "Q1" not in history_s2

    def test_get_or_create_reuses_existing_session(self):
        mm = MemoryManager()
        mm.get_history("s1")
        mm.get_history("s1")
        assert len(mm.sessions) == 1
