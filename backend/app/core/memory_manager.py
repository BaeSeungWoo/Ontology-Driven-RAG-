# app/core/memory_manager.py

from collections import OrderedDict, defaultdict


class MemoryManager:
    # 휘발성 세션 메모리.
    # 서버 프로세스가 살아 있는 동안만 유지되며, window_turns는 user+assistant 한 쌍을 1턴으로 본다.
    def __init__(self, window_turns: int = 3, max_sessions: int = 1000):
        self.store = defaultdict(list)
        # LRU eviction을 위해 세션 사용 순서를 보관한다.
        # 왼쪽이 가장 오래 안 쓴 세션, 오른쪽이 가장 최근 사용한 세션이다.
        self.access_order = OrderedDict()
        self.window_turns = window_turns
        # 세션 key가 무한히 늘지 않도록 MemoryManager 하나가 들고 있을 최대 세션 수를 제한한다.
        self.max_sessions = max_sessions

    def _touch(self, session_id: str):
        # get/add/set처럼 세션이 실제로 사용될 때마다 오른쪽 끝으로 옮겨 최신 사용 세션으로 표시한다.
        self.access_order[session_id] = None
        self.access_order.move_to_end(session_id)

    def _evict_lru_sessions(self):
        # max_sessions 이하이면 아무 것도 지우지 않는다. 0 이하는 제한 없음으로 본다.
        if self.max_sessions <= 0:
            return

        while len(self.store) > self.max_sessions:
            # OrderedDict의 왼쪽 첫 항목이 가장 오래 사용되지 않은 세션이다.
            lru_session_id, _ = self.access_order.popitem(last=False)
            self.clear(lru_session_id)

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
        self._touch(session_id)
        self._evict_lru_sessions()

    def get_history(self, session_id: str):
        history = self.store.get(session_id, [])
        if history:
            self._touch(session_id)
        return history

    def has_history(self, session_id: str) -> bool:
        has_session_history = bool(self.store.get(session_id))
        if has_session_history:
            self._touch(session_id)
        return has_session_history

    def set_history(self, session_id: str, history: list):
        max_messages = self.window_turns * 2
        self.store[session_id] = history[-max_messages:]
        self._touch(session_id)
        self._evict_lru_sessions()

    def clear(self, session_id: str):
        self.store.pop(session_id, None)
        self.access_order.pop(session_id, None)
