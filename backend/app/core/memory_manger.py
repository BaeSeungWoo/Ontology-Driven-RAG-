# app/core/memory_manager.py

from collections import defaultdict

class MemoryManager:
    def __init__(self, window_size: int = 5):
        self.store = defaultdict(list)
        self.window_size = window_size

    def add_user_message(self, session_id: str, content: str):
        self._add(session_id, "user", content)

    def add_ai_message(self, session_id: str, content: str):
        self._add(session_id, "assistant", content)

    def _add(self, session_id, role, content):
        self.store[session_id].append({
            "role": role,
            "content": content
        })

        # 최근 N개 유지
        self.store[session_id] = self.store[session_id][-self.window_size:]

    def get_history(self, session_id: str):
        return self.store.get(session_id, [])

    def clear(self, session_id: str):
        self.store.pop(session_id, None)