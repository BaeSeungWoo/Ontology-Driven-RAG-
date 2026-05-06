# app/core/memory_manager.py

from collections import defaultdict

class MemoryManager:

    # 휘발성 세션 메모리.
    # 서버 프로세스가 살아 있는 동안만 유지되며, window_turns는 user+assistant 한 쌍을 1턴으로 본다.
    def __init__(self, window_turns: int = 3):
        self.store = defaultdict(list)
        self.window_turns = window_turns

    # 답변 생성이 완료된 뒤 user/assistant 한 쌍을 저장한다.
    # max_messages = window_turns * 2 로 잘라 최근 N턴만 유지한다.
    def add_turn(self, session_id: str, question: str, answer: str):
        self.store[session_id].append(
            {"role": "user", "content": question}
        )
        self.store[session_id].append(
            {"role": "assistant", "content": answer}
        )

        max_messages = self.window_turns * 2
        self.store[session_id] = self.store[session_id][-max_messages:]

    def get_history(self, session_id: str):
        return self.store.get(session_id, [])
    
    def has_history(self, session_id: str) -> bool:
        return bool(self.store.get(session_id))

    def set_history(self, session_id: str, history: list):
        max_messages = self.window_turns * 2
        self.store[session_id] = history[-max_messages:]

    def clear(self, session_id: str):
        self.store.pop(session_id, None)