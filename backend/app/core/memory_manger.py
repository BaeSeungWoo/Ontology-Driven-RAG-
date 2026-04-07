# backend/app/core/memory_manager.py

from typing import Dict
from langchain.memory import ConversationBufferWindowMemory


class MemoryManager:
    """세션별 대화 기록을 슬라이딩 윈도우 방식으로 관리합니다."""

    def __init__(self, k: int = 5):
        self.k = k                                          # 유지할 최근 대화 쌍 수
        self.sessions: Dict[str, ConversationBufferWindowMemory] = {}

    # ── 공개 API ──────────────────────────────────────────────────────

    def get_history(self, session_id: str) -> str:
        """service.py → prompt_manager.build()에 주입할 텍스트 형태로 반환합니다."""
        messages = self._get_or_create(session_id).load_memory_variables({})["history"]
        return "\n".join(
            f"{'사용자' if m.type == 'human' else 'AI'}: {m.content}"
            for m in messages
        )

    def save(self, session_id: str, question: str, answer: str) -> None:
        """질문·답변 한 쌍을 저장합니다."""
        self._get_or_create(session_id).save_context(
            {"input": question},
            {"output": answer},
        )

    def clear(self, session_id: str) -> None:
        """세션 대화 기록을 초기화합니다 (대화 리셋 버튼용)."""
        self.sessions.pop(session_id, None)

    # ── 내부 헬퍼 ─────────────────────────────────────────────────────

    def _get_or_create(self, session_id: str) -> ConversationBufferWindowMemory:
        if session_id not in self.sessions:
            self.sessions[session_id] = ConversationBufferWindowMemory(
                k=self.k,
                return_messages=True,
                memory_key="history",
            )
        return self.sessions[session_id]