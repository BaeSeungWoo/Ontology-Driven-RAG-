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
def getHistoryList():
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL01_SP"
            exec_stored_proc(cursor, proc_name)
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
def getHistoryPagination(page, page_size):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL02_SP"
            exec_stored_proc(cursor, proc_name, (page, page_size))

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
def getHistoryQuestioner(questioner, page, page_size):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL03_SP"
            exec_stored_proc(cursor, proc_name, (questioner, page, page_size))

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
def getHistoryQuestionerCounts():
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_SEL04_SP"
            exec_stored_proc(cursor, proc_name)
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
def createSession(questioner, title, llm_model, llm_mode, prompt_no):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()
            proc_name = "dbo.WAFC_WEB_HISTORY_INS01_SP"
            exec_stored_proc(cursor, proc_name, (questioner, title, llm_model, llm_mode, prompt_no))

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
                UPDATE dbo.CHAT_SESSION
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
def updateChatMessage(message_id, content):
    conn = None
    cursor = None
    try:
        with get_db_connection() as conn:
            conn.autocommit = False
            cursor = conn.cursor()

            cursor.execute(
                """
                UPDATE dbo.CHAT_MESSAGE
                SET CONTENT = ?
                WHERE MESSAGE_ID = ?
                """,
                (content, message_id),
            )

            # 메시지 수정 시 해당 세션 최신시간 갱신
            cursor.execute(
                """
                UPDATE s
                SET s.UPDATED_AT = SYSDATETIME()
                FROM dbo.CHAT_SESSION s
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
                    s.LLM_MODE
                FROM dbo.CHAT_MESSAGE m
                INNER JOIN dbo.CHAT_SESSION s ON s.SESSION_ID = m.SESSION_ID
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


#   ===============
#   데일리 리포트
#   ===============

# 통합 프로시저 실행
@with_thread_pool("db")
def getDailyReport(report_date: date, report_id: str, locale: str):
    result_sets = {}
    try:
        with get_db_connection(pool_name="secondary") as conn:
            conn.autocommit = True
            cursor = conn.cursor()
            proc_name = "dbo.SP_DAILY_REPORT_EXECUTE"
            exec_stored_proc(cursor, proc_name, (report_date, report_id, locale))
            # exec_stored_proc(cursor, proc_name, ('2026-03-06','OBI','ko_KR'))
            set_index = 0            
            while True:
                columns = [column[0] for column in cursor.description]
                # 각 row(tuple)를 dict로 변환
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                result_sets[f"tb_{set_index}"] = rows
                set_index += 1
                if not cursor.nextset():
                    break
            cursor.close()
    except Exception as e:
        print(e, 'database getDailyReport() error')
        raise
    return result_sets
