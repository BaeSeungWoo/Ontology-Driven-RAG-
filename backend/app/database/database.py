# -*- coding: utf-8 -*-
"""
데이터베이스 처리 모듈 (pyodbc 연결 풀 전용)
기존 pymssql에서 pyodbc 연결 풀로 완전 변환
"""

import os
import json
import pandas as pd
from .connection_pool import get_db_connection #, get_pool
from .thread_pool_manager import with_thread_pool

# pyodbc용 stored procedure 실행 헬퍼 함수
def exec_stored_proc(cursor, proc_name, params=None):
    """
    pyodbc에서 stored procedure를 실행하는 헬퍼 함수
    pymssql의 callproc과 동일한 인터페이스 제공
    """
    try:
        if params is None:
            # 파라미터 없는 경우
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

# 기존 callproc 메서드를 cursor에 동적으로 추가
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
