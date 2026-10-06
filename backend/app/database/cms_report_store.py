import json
import os
from datetime import date, datetime
from decimal import Decimal

from app.database.connection_pool import get_db_connection

# Fixed test dataset: assume today is 2026-08-21.
REPORT_DATE = date(2026, 8, 20)


def _json_default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Unsupported report value: {type(value).__name__}")


def get_report(report_date: date = REPORT_DATE):
    factory_id = os.environ["FACTORY_ID"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT STATUS, MODEL_CONFIG, MODEL_NAME, REPORT_JSON, VIEWS_JSON,
                       STARTED_AT, COMPLETED_AT, ERROR_MESSAGE,
                       CASE WHEN STATUS = 'GENERATING' AND STARTED_AT < DATEADD(minute, -10, SYSUTCDATETIME())
                            THEN 1 ELSE 0 END
                FROM [PROMPT].[dbo].[CMS_DAILY_REPORT] WHERE FACTORY_ID = ? AND REPORT_DATE = ?
            """, factory_id, report_date)
            row = cursor.fetchone()
            if row is None:
                return None
            return {
                "factoryId": factory_id, "reportDate": report_date.isoformat(),
                "status": "FAILED" if row[8] else row[0],
                "config": row[1], "modelName": row[2],
                "report": json.loads(row[3]) if row[3] else None,
                "views": json.loads(row[4]) if row[4] else None,
                "startedAt": row[5].isoformat() + "Z",
                "completedAt": row[6].isoformat() + "Z" if row[6] else None,
                "errorMessage": "생성이 중단되었습니다. 다시 생성해 주세요." if row[8] else row[7],
            }
        finally:
            cursor.close()


def claim_report(config: str, model_name: str, force: bool = False, report_date: date = REPORT_DATE):
    """Reserve one generation across processes; return its DB timestamp as an ownership token."""
    factory_id = os.environ["FACTORY_ID"]
    with get_db_connection() as conn:
        conn.autocommit = False
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT STATUS,
                       CASE WHEN STARTED_AT < DATEADD(minute, -10, SYSUTCDATETIME()) THEN 1 ELSE 0 END
                FROM [PROMPT].[dbo].[CMS_DAILY_REPORT] WITH (UPDLOCK, HOLDLOCK)
                WHERE FACTORY_ID = ? AND REPORT_DATE = ?
            """, factory_id, report_date)
            row = cursor.fetchone()
            if row and ((row[0] == "GENERATING" and not row[1]) or (row[0] == "COMPLETED" and not force)):
                conn.commit()
                return None
            if row:
                cursor.execute("""
                    UPDATE [PROMPT].[dbo].[CMS_DAILY_REPORT]
                    SET STATUS = 'GENERATING', MODEL_CONFIG = ?, MODEL_NAME = ?,
                        REPORT_JSON = NULL, VIEWS_JSON = NULL, STARTED_AT = SYSUTCDATETIME(),
                        COMPLETED_AT = NULL, ERROR_MESSAGE = NULL
                    OUTPUT inserted.STARTED_AT
                    WHERE FACTORY_ID = ? AND REPORT_DATE = ?
                """, config, model_name, factory_id, report_date)
            else:
                cursor.execute("""
                    INSERT INTO [PROMPT].[dbo].[CMS_DAILY_REPORT] (FACTORY_ID, REPORT_DATE, MODEL_CONFIG, MODEL_NAME)
                    OUTPUT inserted.STARTED_AT VALUES (?, ?, ?, ?)
                """, factory_id, report_date, config, model_name)
            token = cursor.fetchone()[0]
            conn.commit()
            return token
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.autocommit = True


def save_report(token, report, views, completed=False, report_date: date = REPORT_DATE):
    factory_id = os.environ["FACTORY_ID"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE [PROMPT].[dbo].[CMS_DAILY_REPORT]
                SET REPORT_JSON = ?, VIEWS_JSON = ?, STATUS = ?,
                    COMPLETED_AT = CASE WHEN ? = 1 THEN SYSUTCDATETIME() ELSE NULL END
                WHERE FACTORY_ID = ? AND REPORT_DATE = ? AND STARTED_AT = ? AND STATUS = 'GENERATING'
            """, json.dumps(report, ensure_ascii=False, default=_json_default),
                json.dumps(views, ensure_ascii=False, default=_json_default),
                "COMPLETED" if completed else "GENERATING", int(completed), factory_id, report_date, token)
        finally:
            cursor.close()


def fail_report(token, message, report_date: date = REPORT_DATE):
    factory_id = os.environ["FACTORY_ID"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE [PROMPT].[dbo].[CMS_DAILY_REPORT] SET STATUS = 'FAILED', ERROR_MESSAGE = ?
                WHERE FACTORY_ID = ? AND REPORT_DATE = ? AND STARTED_AT = ? AND STATUS = 'GENERATING'
            """, message, factory_id, report_date, token)
        finally:
            cursor.close()


def set_model(token, config, model_name, report_date: date = REPORT_DATE):
    factory_id = os.environ["FACTORY_ID"]
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE [PROMPT].[dbo].[CMS_DAILY_REPORT] SET MODEL_CONFIG = ?, MODEL_NAME = ?
                WHERE FACTORY_ID = ? AND REPORT_DATE = ? AND STARTED_AT = ? AND STATUS = 'GENERATING'
            """, config, model_name, factory_id, report_date, token)
        finally:
            cursor.close()
