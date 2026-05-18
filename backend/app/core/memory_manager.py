# app/core/memory_manager.py

from collections import OrderedDict, defaultdict


SUMMARY_PREFIX = "[이전 대화 요약]"


class MemoryManager:
    # 세션별 대화 메모리
    # 서버 프로세스가 살아 있는 동안만 유지되며, window_turns는 "요약 1개" 또는 "user+assistant 한 쌍"을 1슬롯으로 본다.
    def __init__(self, window_turns: int = 5, max_sessions: int = 100):
        self.store = defaultdict(list)
        # LRU eviction을 위해 세션 사용 순서를 보관한다.
        # 왼쪽이 가장 오래된 세션, 오른쪽이 가장 최근 사용 세션이다.
        self.access_order = OrderedDict()
        self.window_turns = window_turns
        # 세션 key가 무한히 늘지 않도록 MemoryManager 하나가 들고 있을 최대 세션 수를 제한한다.
        self.max_sessions = max_sessions

    def _touch(self, session_id: str):
        # get/add/set처럼 세션이 실제로 사용될 때마다 오른쪽 끝으로 옮겨 최신 사용 세션으로 표시한다.
        self.access_order[session_id] = None
        self.access_order.move_to_end(session_id)

    def _evict_lru_sessions(self):
        # max_sessions 이하이면 아무 것도 지우지 않는다. 0 이하이면 제한 없음으로 본다.
        if self.max_sessions <= 0:
            return

        while len(self.store) > self.max_sessions:
            # OrderedDict의 왼쪽 첫 항목이 가장 오래 사용되지 않은 세션이다.
            lru_session_id, _ = self.access_order.popitem(last=False)
            self.clear(lru_session_id)

    def _is_summary_message(self, message: dict) -> bool:
        return str(message.get("content", "")).startswith(SUMMARY_PREFIX)

    def _split_slots(self, history: list) -> list[list]:
        slots = []
        index = 0

        while index < len(history):
            message = history[index]

            # 압축 요약은 하나의 컨텍스트 슬롯으로 계산한다.
            if self._is_summary_message(message):
                slots.append([message])
                index += 1
                continue

            # user + assistant 한 쌍을 하나의 대화 턴 슬롯으로 계산한다.
            if (
                message.get("role") == "user"
                and index + 1 < len(history)
                and history[index + 1].get("role") == "assistant"
                and not self._is_summary_message(history[index + 1])
            ):
                slots.append([message, history[index + 1]])
                index += 2
                continue

            slots.append([message])
            index += 1

        return slots

    def _trim_to_window(self, history: list) -> list:
        slots = self._split_slots(history)
        trimmed_slots = slots[-self.window_turns:]
        return [message for slot in trimmed_slots for message in slot]

    def get_slot_count(self, session_id: str) -> int:
        history = self.store.get(session_id, [])
        return len(self._split_slots(history))

    def should_summarize(self, session_id: str) -> bool:
        return self.get_slot_count(session_id) >= self.window_turns

    def replace_with_summary(self, session_id: str, summary: str):
        # 모든 내용을 제거하고, 요약 내용[1턴]을 넣어준다.
        self.store[session_id] = [
            {
                "role": "user",
                "content": f"{SUMMARY_PREFIX}\n{summary}",
            }
        ]
        self._touch(session_id) # 세션 사용순서 최신으로 갱신
        self._evict_lru_sessions() # 세션 수가 100개 넘으면 가장 안쓴 세션을 제거

    # 답변 생성이 끝난 뒤 현재 user/assistant 한 쌍을 저장한다.
    # 요약 1개 또는 user/assistant 한 쌍을 1슬롯으로 보고 최근 window_turns 슬롯만 유지한다.
    def add_turn(self, session_id: str, question: str, answer: str):
        self.store[session_id].append(
            {"role": "user", "content": question}
        )
        self.store[session_id].append(
            {"role": "assistant", "content": answer}
        )

        self.store[session_id] = self._trim_to_window(self.store[session_id])
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
        self.store[session_id] = self._trim_to_window(history)
        self._touch(session_id)
        self._evict_lru_sessions()

    def clear(self, session_id: str):
        self.store.pop(session_id, None)
        self.access_order.pop(session_id, None)
