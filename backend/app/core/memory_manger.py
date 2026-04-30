# app/core/memory_manager.py

from collections import defaultdict
# 시나리오
# 1. 세션 첫 ask 호출
#    - MemoryManager에 session_id가 없음
#    - DB에서 최근 N턴 조회
#    - MemoryManager에 bootstrap

# 2. 이후 같은 session_id ask 호출
#    - DB 조회 안 함
#    - MemoryManager에 있는 history 사용

# 3. 답변 완료 후
#    - MemoryManager에 현재 user/assistant 저장

# 4. 일정 길이 초과
#    - 오래된 대화는 summary로 압축
#    - 최근 몇 턴은 원문 유지

class MemoryManager:
#   DB
#     영구 저장소
#     세션이 다시 열렸을 때 과거 대화를 일부 복원하는 용도

#   CHAT_HISTORY 한 행 = 하나의 대화 세션
#   CHAT_MESSAGE 여러 행 = 그 세션 안의 대화 로그
#   MemoryManager store 한 entry = 그 세션의 휘발성 메모리
#   
#   MemoryManager
#     휘발성 저장소
#     현재 서버 프로세스가 살아 있는 동안만 유지
#     ask 호출 사이에서 최근 대화 또는 요약을 들고 있음

    # def __init__(self, window_size: int = 5):
        # self.window_size = window_size
    def __init__(self, window_turns: int = 3):
        self.store = defaultdict(list)
        self.window_turns = window_turns

    def add_turn(self, session_id: str, question: str, answer: str):
        self.store[session_id].append(
            {"role": "user", "content": question}
        )
        self.store[session_id].append(
            {"role": "assistant", "content": answer}
        )

        max_messages = self.window_turns * 2
        self.store[session_id] = self.store[session_id][-max_messages:]

    # def add_user_message(self, session_id: str, content: str):
    #     self._add(session_id, "user", content)

    # def add_ai_message(self, session_id: str, content: str):
    #     self._add(session_id, "assistant", content)

    # def _add(self, session_id, role, content):
    #     self.store[session_id].append({
    #         "role": role,
    #         "content": content
    #     })

    #     # 최근 N개 유지
    #     self.store[session_id] = self.store[session_id][-self.window_size:]

    def get_history(self, session_id: str):
        return self.store.get(session_id, [])

    def clear(self, session_id: str):
        self.store.pop(session_id, None)