# -*- coding: utf-8 -*-
"""
데이터베이스 처리 모듈 (pyodbc 연결 전용)
기존 pymssql에서 pyodbc 연결 방식으로 전환
"""

import os
import json
import pandas as pd
from .connection_pool import get_db_connection #, get_pool
from .thread_pool_manager import with_thread_pool
from .daily_report_sections_spec import (
    DAILY_REPORT_SECTION_TEMPLATE,
    DAILY_REPORT_SECTION_KEY_MAP,
)
from datetime import date

# pyodbc용 stored procedure 실행 헬퍼 함수
def exec_stored_proc(cursor, proc_name, params=None):
    """
    pyodbc에서 stored procedure를 실행하는 헬퍼 함수
    pymssql의 callproc과 유사한 인터페이스 제공
    """
    try:
        if params is None:
            # 파라미터가 없는 경우
            cursor.execute(f"EXEC {proc_name}")
        else:
            # 파라미터가 있는 경우
            if isinstance(params, (list, tuple)):
                placeholders = ",".join(["?"] * len(params))
                cursor.execute(f"EXEC {proc_name} {placeholders}", params)
            else:
                # 단일 파라미터인 경우
                cursor.execute(f"EXEC {proc_name} ?", (params,))
    except Exception as e:
        print(f"Stored procedure execution error: {proc_name}, params: {params}, error: {e}")
        raise

# 기존 callproc 메서드를 cursor 객체에 동적으로 추가
def add_callproc_to_cursor(cursor):
    """cursor 객체에 callproc 메서드를 동적으로 추가"""
    def callproc(proc_name, params=None):
        return exec_stored_proc(cursor, proc_name, params)
    cursor.callproc = callproc
    return cursor

@with_thread_pool("db")
# 프롬프트 목록 조회
def getPromptList():
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_PROMPT_SEL01_SP"
            exec_stored_proc(cursor, proc_name)
            results = cursor.fetchall()
            cursor.close()
    except Exception as e:
        print(e, 'database getPromptList() error')
        return []
    finally :
        return results

# 백엔드 > 사용자 프롬프트 내용 조회
@with_thread_pool("db")
def getUserPrompt(promptNo):
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT PROMPT_TXT
                FROM [PROMPT].[dbo].[PROMPT_TB]
                WHERE PROMPT_NO = ?
                """,
                (promptNo,),
            )
            row = cursor.fetchone()
            cursor.close()

            if row is None:
                return None
            return row[0]
    except Exception as e:
        print(e, 'database getUserPrompt() error')
        return None

# 프롬프트 정보 추가
@with_thread_pool("db")
def addPrompt(title, content, create_user) :
    try  :
        with get_db_connection() as conn :
            conn.autocommit = False
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_PROMPT_INS01_SP"
            exec_stored_proc(cursor, proc_name, (title,content,create_user))
            conn.commit()
            cursor.close()
            return 1
    except Exception as e :
        conn.rollback()
        print(e, 'database addPrompt() Error')
        return 0

# 프롬프트 정보 수정
@with_thread_pool("db")
def updatePrompt(updatePrompt) :
    try  :
        with get_db_connection() as conn :
            conn.autocommit = False
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_PROMPT_SAV01_SP"
            exec_stored_proc(cursor, proc_name, (updatePrompt['PROMPT_NAME'], updatePrompt['PROMPT_TXT'], updatePrompt['CREATE_USER'], updatePrompt['PROMPT_NO']))
            conn.commit()
            cursor.close()
            return 1
    except Exception as e :
        conn.rollback()
        print(e, 'database addPrompt() Error')
        return 0

# 대화 이력(세션 정보) 목록 조회
@with_thread_pool("db")
def getHistoryList(machine_code):
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL01_SP"
            exec_stored_proc(cursor, proc_name, (machine_code,))
            results = cursor.fetchall()
            cursor.close()
    except Exception as e:
        print(e, 'database getHistoryList() error')
        return []
    finally :
        return results


# 대화 이력 페이지 조회 (프로시저 기반)
# - 1st result set: rows (SESSION_ID, QUESTIONER, TITLE, LLM_MODEL, LLM_MODE, PROMPT_NO, CREATED_AT, UPDATED_AT, PROMPT_NAME)
# - 2nd result set: meta (TOTAL_COUNT, TOTAL_PAGES, PAGE, PAGE_SIZE)
@with_thread_pool("db")
def getHistoryPagination(page, page_size, machine_code):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL02_SP"
            exec_stored_proc(cursor, proc_name, (page, page_size, machine_code))

            rows = cursor.fetchall()
            total_count = len(rows)
            total_pages = 1
            current_page = page
            current_page_size = page_size

            # 메타 result set이 있으면 우선 사용
            if cursor.nextset():
                meta = cursor.fetchone()
                if meta is not None:
                    total_count = int(meta[0]) if len(meta) > 0 and meta[0] is not None else total_count
                    total_pages = int(meta[1]) if len(meta) > 1 and meta[1] is not None else total_pages
                    current_page = int(meta[2]) if len(meta) > 2 and meta[2] is not None else current_page
                    current_page_size = int(meta[3]) if len(meta) > 3 and meta[3] is not None else current_page_size

            return {
                "rows": rows,
                "total_count": total_count,
                "total_pages": max(1, total_pages),
                "page": max(1, current_page),
                "page_size": max(1, current_page_size),
            }
    except Exception as e:
        print(f"database getHistoryPagination() error: page={page}, page_size={page_size}, error={e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


# 질문자 기준 대화 이력 페이지 조회 (프로시저 기반)
# - 1st result set: rows
# - 2nd result set: meta (TOTAL_COUNT, TOTAL_PAGES, PAGE, PAGE_SIZE)
@with_thread_pool("db")
def getHistoryQuestioner(questioner, page, page_size, machine_code):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL03_SP"
            exec_stored_proc(cursor, proc_name, (questioner, page, page_size, machine_code))

            rows = cursor.fetchall()
            total_count = len(rows)
            total_pages = 1
            current_page = page
            current_page_size = page_size

            if cursor.nextset():
                meta = cursor.fetchone()
                if meta is not None:
                    total_count = int(meta[0]) if len(meta) > 0 and meta[0] is not None else total_count
                    total_pages = int(meta[1]) if len(meta) > 1 and meta[1] is not None else total_pages
                    current_page = int(meta[2]) if len(meta) > 2 and meta[2] is not None else current_page
                    current_page_size = int(meta[3]) if len(meta) > 3 and meta[3] is not None else current_page_size

            return {
                "rows": rows,
                "total_count": total_count,
                "total_pages": max(1, total_pages),
                "page": max(1, current_page),
                "page_size": max(1, current_page_size),
            }
    except Exception as e:
        print(
            f"database getHistoryQuestioner() error: questioner={questioner}, page={page}, page_size={page_size}, error={e}"
        )
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


# 질문자별 이력 건수 조회 (프로시저 기반)
# result set: (QUESTIONER, COUNT)
@with_thread_pool("db")
def getHistoryQuestionerCounts(machine_code):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL04_SP"
            exec_stored_proc(cursor, proc_name, (machine_code,))
            return cursor.fetchall()
    except Exception as e:
        print(f"database getHistoryQuestionerCounts() error: {e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

# 신규 대화 세션 생성
@with_thread_pool("db")
def createSession(questioner, title, llm_model, llm_mode, prompt_no, machine_code):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_INS01_SP"
            exec_stored_proc(cursor, proc_name, (questioner, title, llm_model, llm_mode, prompt_no, machine_code))

            # 프로시저에서 OUTPUT INSERTED.SESSION_ID로 반환된 값 받기
            row = cursor.fetchone()

            conn.commit()

            if row is None:
                raise Exception("session_id 반환값이 없습니다.")

            session_id = int(row[0])
            return session_id

    except Exception as e:
        if conn:
            conn.rollback()
        print(
            f"database createSession() Error: questioner={questioner}, title={title}, llm_model={llm_model}, llm_mode={llm_mode}, prompt_no={prompt_no}, error={e}"
        )
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                # with 블록 종료로 connection이 먼저 닫힌 경우 cursor.close()가 실패할 수 있음
                pass


@with_thread_pool("db")
def deleteChatSession(session_id):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_DEL01_SP"
            exec_stored_proc(cursor, proc_name, (session_id,))
            conn.commit()
            return 1
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"database deleteChatSession() Error: session_id={session_id}, error={e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


# 세션 id 및 소속 장비코드
@with_thread_pool("db")
def getChatSessionInfo(session_id):
    with get_db_connection() as conn:
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                SESSION_ID,
                MACHINE_CODE,
                QUESTIONER,
                TITLE
            FROM dbo.CHAT_HISTORY
            WHERE SESSION_ID = ?
            """,
            (session_id,),
        )

        row = cursor.fetchone()
        cursor.close()

    if not row:
        return None

    return {
        "session_id": int(row[0]),
        "machine_code": row[1],
        "questioner": row[2],
        "title": row[3],
    }

# CHAT_MESSAGE 질문 / 답변(Temp) 저장
@with_thread_pool("db")
def createChatMessage(session_id, role, content):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO dbo.CHAT_MESSAGE (SESSION_ID, ROLE, CONTENT)
                OUTPUT INSERTED.MESSAGE_ID
                VALUES (?, ?, ?)
                """,
                (session_id, role, content),
            )
            row = cursor.fetchone()
            if row is None:
                raise Exception("message_id 반환값이 없습니다.")
            message_id = int(row[0])

            # 메시지가 추가될 때 세션 최신시간 갱신
            cursor.execute(
                """
                UPDATE dbo.CHAT_HISTORY
                SET UPDATED_AT = SYSDATETIME()
                WHERE SESSION_ID = ?
                """,
                (session_id,),
            )

            conn.commit()
            return message_id
    except Exception as e:
        if conn:
            conn.rollback()
        print(
            f"database createChatMessage() Error: session_id={session_id}, role={role}, error={e}"
        )
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


# CHAT_MESSAGE 답변 완료내용 갱신
@with_thread_pool("db")
def updateChatMessage(message_id, content, metadata_json=None):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()

            if metadata_json is None:
                cursor.execute(
                    """
                    UPDATE dbo.CHAT_MESSAGE
                    SET CONTENT = ?
                    WHERE MESSAGE_ID = ?
                    """,
                    (content, message_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE dbo.CHAT_MESSAGE
                    SET CONTENT = ?,
                        METADATA = ?
                    WHERE MESSAGE_ID = ?
                    """,
                    (content, metadata_json, message_id),
                )

            # 메시지 수정 시 해당 세션 최신시간 갱신
            cursor.execute(
                """
                UPDATE s
                SET s.UPDATED_AT = SYSDATETIME()
                FROM dbo.CHAT_HISTORY s
                INNER JOIN dbo.CHAT_MESSAGE m ON m.SESSION_ID = s.SESSION_ID
                WHERE m.MESSAGE_ID = ?
                """,
                (message_id,),
            )

            conn.commit()
            return 1
    except Exception as e:
        if conn:
            conn.rollback()
        print(
            f"database updateChatMessage() Error: message_id={message_id}, error={e}"
        )
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass


# 세션별 채팅 메시지 조회
@with_thread_pool("db")
def getChatMessagesBySession(session_id):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    m.MESSAGE_ID,
                    m.SESSION_ID,
                    m.ROLE,
                    m.CONTENT,
                    m.CREATED_AT,
                    s.QUESTIONER,
                    s.LLM_MODEL,
                    s.LLM_MODE,
                    m.METADATA
                FROM dbo.CHAT_MESSAGE m
                INNER JOIN dbo.CHAT_HISTORY s ON s.SESSION_ID = m.SESSION_ID
                WHERE m.SESSION_ID = ?
                ORDER BY m.CREATED_AT ASC, m.MESSAGE_ID ASC
                """,
                (session_id,),
            )
            return cursor.fetchall()
    except Exception as e:
        print(f"database getChatMessagesBySession() Error: session_id={session_id}, error={e}")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

# 메세지 업데이트 시 세션 검증용 세션 id 추출
@with_thread_pool("db")
def getSessionIdByMessageId(message_id):
    with get_db_connection() as conn:
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT SESSION_ID
            FROM dbo.CHAT_MESSAGE
            WHERE MESSAGE_ID = ?
            """,
            (message_id,),
        )
        row = cursor.fetchone()
        cursor.close()

    if not row:
        return None

    return int(row[0])


#   ===============
#   데일리 리포트
#   ===============

# 데일리 리포트 결과 조회
@with_thread_pool("db")
def getDailyReportResult(report_date: date, report_id: str, locale: str):
    result_sets = {}
    try:
        with get_db_connection(pool_name="secondary") as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.SP_DAILY_REPORT_RESULT_SELECT"
            exec_stored_proc(cursor, proc_name, (report_date, report_id, locale))
            set_index = 0
            while True:
                if cursor.description is None:
                    result_sets[f"tb_{set_index}"] = []
                else:
                    columns = [column[0] for column in cursor.description]
                    # 각 row(tuple)를 dict로 변환
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                    result_sets[f"tb_{set_index}"] = rows
                set_index += 1
                if not cursor.nextset():
                    break
            cursor.close()
    except Exception as e:
        print(e, "database getDailyReportResult() error")
        raise
    return result_sets

# 데일리 리포트 결과 저장(없을 때만 생성)
@with_thread_pool("db")
def saveDailyReportResult(report_date: date, report_id: str, locale: str, context_json: str):
    conn = None
    cursor = None
    try:
        with get_db_connection(pool_name="secondary") as conn:
            conn.autocommit = False
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO dbo.DAILY_REPORT_RESULT (
                    REPORT_DATE, REPORT_ID, LOCALE, CONTEXT_JSON, CREATED_AT, UPDATED_AT
                )
                SELECT ?, ?, ?, ?, SYSDATETIME(), SYSDATETIME()
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dbo.DAILY_REPORT_RESULT
                    WHERE REPORT_DATE = ?
                      AND REPORT_ID = ?
                      AND LOCALE = ?
                )
                """,
                (
                    report_date,
                    report_id,
                    locale,
                    context_json,
                    report_date,
                    report_id,
                    locale,
                ),
            )
            conn.commit()
            return 1
    except Exception as e:
        if conn:
            conn.rollback()
        print(e, "database saveDailyReportResult() error")
        raise
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

# 통합 프로시저 실행
@with_thread_pool("db")
def getDailyReport(report_date: date, report_id: str, locale: str):
    """
    데일리 리포트를 sections 형태로 만들어 반환한다.

    흐름:
    1) 프로시저 실행
    2) result set을 하나씩 읽어서 rows(list[dict]) 생성
    3) rows의 첫 행에서 DOMAIN_CD/STEP_NO를 읽어 섹션 위치를 찾음
    4) 찾은 섹션에 rows를 넣음
    5) 모든 result set 처리 후 sections 반환
    """
    try:
        with get_db_connection(pool_name="secondary") as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.SP_DAILY_REPORT_EXECUTE"
            exec_stored_proc(cursor, proc_name, (report_date, report_id, locale))
            # exec_stored_proc(cursor, proc_name, ('2026-03-06','OBI','ko_KR'))
            sections = _init_daily_report_sections()
            while True:
                # 컬럼 정보가 없으면(데이터성 결과가 아니면) 빈 rows로 본다.
                if cursor.description is None:
                    rows = []
                else:
                    columns = [column[0] for column in cursor.description]
                    # 튜플 행을 {컬럼명: 값} 형태로 변환한다.
                    rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

                # rows 전체는 "하나의 result set 묶음"이다.
                # first_row는 "분류(매핑)용"으로만 쓰고, 실제 저장은 rows 전체를 넣는다.
                first_row = _find_first_row(rows)
                if first_row is not None:
                    # 예: DOMAIN_CD=PROD, STEP_NO=3
                    # 비교/매핑 정확도를 위해 문자열 대문자/정수 형태로 정규화한다.
                    domain_cd = str(first_row.get("DOMAIN_CD", "")).strip().upper()
                    step_no = _to_int_or_none(first_row.get("STEP_NO"))

                    # 명세 테이블에서 "(도메인, 스텝)"에 해당하는 섹션 위치를 찾는다.
                    # 예: ("PROD", 3) -> ("prod", "processBottleneck")
                    mapped = DAILY_REPORT_SECTION_KEY_MAP.get((domain_cd, step_no))
                    if mapped is not None:
                        domain_key, section_key = mapped

                        # 현재 result set의 모든 행(rows)을 해당 섹션에 누적한다.
                        # 동일 섹션으로 여러 result set이 올 수 있어 extend를 사용한다.
                        sections[domain_key][section_key].extend(rows)
                    else:
                        # 명세(KEY_MAP)에 없는 조합은 현재 구조에 넣을 위치가 없어서 버린다.
                        # 예: ("PROD", 8)
                        pass

                if not cursor.nextset():
                    break
            cursor.close()
    except Exception as e:
        print(e, 'database getDailyReport() error')
        raise

    # 최종 결과는 sections만 반환한다.
    return sections

def _init_daily_report_sections():
    """
    빈 sections 뼈대를 새로 만든다.
    (요청마다 새 객체를 만들어야 데이터가 섞이지 않는다.)
    """
    return {
        domain: {section: [] for section in section_map.keys()}
        for domain, section_map in DAILY_REPORT_SECTION_TEMPLATE.items()
    }

def _to_int_or_none(value):
    """
    값을 정수로 바꾼다.
    실패하면 None을 반환한다.
    """
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None

def _find_first_row(rows):
    """
    rows(list[dict])에서 첫 dict 행을 돌려준다.
    (섹션 매핑에 DOMAIN_CD/STEP_NO를 쓰기 위해 사용)
    """
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict):
            return row
    return None

#region CMS 데이터 조회

CMS_DASHBOARD_VIEW_TABLES = {
    "daily-planned-rate": "dbo.V_CMS_DAILY_PLANNED_RATE",
    "hourly-rate": "dbo.V_CMS_HOURLY_RATE",
    "daily-alarm-summary": "dbo.V_CMS_DAILY_ALARM_SUMMARY",
    "alarm-machine-top3": "dbo.V_CMS_DAILY_ALARM_MACHINE_TOP3",
    "longest-alarm-top3": "dbo.V_CMS_DAILY_LONGEST_ALARM_TOP3",
}

CMS_DASHBOARD_VIEW_ORDER_BY = {
    "daily-planned-rate": "WORK_DATE ASC",
    "hourly-rate": "WORK_DATE ASC, HOUR_SEQ ASC",
    "daily-alarm-summary": "WORK_DATE ASC, ALARM_RANK ASC",
    "alarm-machine-top3": "WORK_DATE ASC, ALARM_RANK ASC",
    "longest-alarm-top3": "WORK_DATE ASC, ALARM_RANK ASC",
}

def _get_cms_dashboard_view_rows(view_key: str) -> list[dict]:
    table_name = CMS_DASHBOARD_VIEW_TABLES.get(view_key)
    order_by = CMS_DASHBOARD_VIEW_ORDER_BY.get(view_key)
    if table_name is None or order_by is None:
        raise ValueError(f"Unsupported CMS view: {view_key}")

    cursor = None

    try:
        with get_db_connection(pool_name="third") as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute(f"SELECT * FROM {table_name} ORDER BY {order_by}")

            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    except Exception as e:
        print(e, f"database CMS view query error: view_key={view_key}")
        raise

    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass

@with_thread_pool("db")
def getCmsDashboardView(view_key: str) -> list[dict]:
    return _get_cms_dashboard_view_rows(view_key)

@with_thread_pool("db")
def getCmsDashboardViews() -> dict[str, list[dict]]:
    return {
        view_key: _get_cms_dashboard_view_rows(view_key)
        for view_key in CMS_DASHBOARD_VIEW_TABLES
    }

#endregion
