import json


def manual_query_messages(question, history):
    instruction = (
        "현재 질문을 CNC 매뉴얼 검색용 독립 질문으로 복원한다. "
        "현재 질문만으로 대상과 작업이 명확하거나 주제가 바뀌면 원문을 그대로 반환한다. "
        "생략되었거나 지시어로 표현된 장비 부위, 작업, 조건만 대화에서 찾아 보완한다. "
        "현재 질문이 바꾼 상태와 부정, 사용자가 제시한 식별자는 그대로 보존한다. "
        "답변이나 원인 후보를 쓰지 말고, 이전 답변의 추측, 예시 알람·신호 번호를 끌어오지 않는다. "
        'JSON 객체 {"query":"검색할 질문"}만 반환한다.'
    )
    return [
        {"role": "system", "content": instruction},
        {"role": "user", "content": json.dumps({"대화": history, "현재 질문": question}, ensure_ascii=False)},
    ]
