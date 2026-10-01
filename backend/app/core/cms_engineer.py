"""Bounded alarm history and matching manual evidence for the test window."""

import asyncio
import json
import re
from datetime import datetime, timedelta

from app.core.cms_context import CMS_TEST_DATE
from pipeline.ingestion.machine_resolver import build_doc_to_machine_index, _resolve_machine_code


def alarm_codes(question):
    return list(dict.fromkeys(re.findall(r"\b[A-Z]{1,6}\d{3,}(?:\.\d+)?\b", question.upper())))[:5]


def contains_code(text, code):
    return re.search(r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])", text, re.I) is not None


def load_engineer_snapshot(machine_code, requested_codes=()):
    from app.database.connection_pool import get_db_connection

    if not machine_code or machine_code == "ALL":
        raise ValueError("현재 장비를 지정해야 합니다.")
    with get_db_connection(pool_name="third") as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT MACHINE_NAME FROM dbo.TDAM0001 WHERE MACHINE_CODE = ?", (machine_code,))
            machine = cursor.fetchone()
            if not machine:
                raise ValueError("현재 장비의 CMS 등록 정보가 없습니다.")
            cursor.execute("""SELECT CONVERT(TIME(0), CODE_DESC) FROM dbo.TDAA0001_TBL
                WHERE GROUP_GB = 'SET' AND CODE_NO = 'STN_DAY_START' AND USE_FLAG = 'Y'""")
            setting = cursor.fetchone()
            if not setting:
                raise ValueError("CMS 작업일 시작 시각이 없습니다.")
            start = datetime.combine(CMS_TEST_DATE - timedelta(days=7), setting[0])
            end = datetime.combine(CMS_TEST_DATE + timedelta(days=1), setting[0])
            window = (machine_code, start, end)
            cursor.execute("""SELECT COUNT_BIG(*),
                COALESCE(SUM(CASE WHEN STATUS = '2' THEN CAST(1 AS BIGINT) ELSE 0 END), 0)
                FROM dbo.TDAM0002 WHERE MACHINE_CODE = ? AND OCCUR_DATE >= ? AND OCCUR_DATE < ?""", window)
            history_rows, total_events = cursor.fetchone()
            # Count the entire window in SQL; only selected summaries and samples leave the DB.
            priority = ",".join("?" for _ in requested_codes)
            order = f"CASE WHEN ALARM_CODE IN ({priority}) THEN 0 ELSE 1 END," if requested_codes else ""
            cursor.execute(f"""SELECT TOP (5) ALARM_CODE, COUNT_BIG(*) AS EVENT_COUNT,
                MAX(OCCUR_DATE) AS LAST_OCCURRED,
                SUM(CASE WHEN FINISH_DATE >= OCCUR_DATE AND FINISH_DATE < ?
                    THEN DATEDIFF_BIG(SECOND, OCCUR_DATE, FINISH_DATE) ELSE NULL END) AS CLOSED_SECONDS,
                SUM(CASE WHEN FINISH_DATE IS NULL OR FINISH_DATE >= ? THEN 1 ELSE 0 END) AS UNFINISHED
                FROM dbo.TDAM0002
                WHERE MACHINE_CODE = ? AND OCCUR_DATE >= ? AND OCCUR_DATE < ? AND STATUS = '2'
                GROUP BY ALARM_CODE ORDER BY {order} EVENT_COUNT DESC, LAST_OCCURRED DESC, ALARM_CODE""",
                (end, end, *window, *requested_codes))
            alarms = []
            for code, count, last, seconds, unfinished in cursor.fetchall():
                code_filter = "ALARM_CODE = ?" if code is not None else "ALARM_CODE IS NULL"
                params = (*window, code) if code is not None else window
                cursor.execute(f"""SELECT TOP (3) OCCUR_DATE, FINISH_DATE
                    FROM dbo.TDAM0002 WHERE MACHINE_CODE = ? AND OCCUR_DATE >= ? AND OCCUR_DATE < ?
                    AND STATUS = '2' AND {code_filter} ORDER BY OCCUR_DATE DESC, FINISH_DATE DESC""", params)
                events = [{"occurred_at": occurred.isoformat(),
                           "finished_at": finished.isoformat() if finished and finished < end else None}
                          for occurred, finished in cursor.fetchall()]
                cursor.execute(f"""SELECT DATEPART(HOUR, OCCUR_DATE), COUNT_BIG(*) FROM dbo.TDAM0002
                    WHERE MACHINE_CODE = ? AND OCCUR_DATE >= ? AND OCCUR_DATE < ? AND STATUS = '2'
                    AND {code_filter} GROUP BY DATEPART(HOUR, OCCUR_DATE) ORDER BY 1""", params)
                hourly_counts = [list(row) for row in cursor.fetchall()]
                cursor.execute("""SELECT A.ALARM_DETAILS, A.ALARM_ACTION
                    FROM dbo.TDAA0002_TBL A
                    JOIN dbo.TDAM0001 M ON M.MACHINE_SYS = A.MACHINE_SYS AND M.MACHINE_VER = A.MACHINE_VER
                    WHERE M.MACHINE_CODE = ? AND A.ALARM_CODE = ?""", (machine_code, code))
                definition = cursor.fetchone()
                alarms.append({"code": code, "count": count, "last_occurred_at": last.isoformat(),
                               "definition_registered": definition is not None,
                               "alarm_name": definition[0] if definition else None,
                               "alarm_description": definition[1] if definition else None,
                               "closed_duration_seconds": seconds, "unfinished_records_at_cutoff": unfinished,
                               "hourly_counts": hourly_counts, "recent_events": events})
            # Separate as-of observation: it may precede the history window and is not live status.
            cursor.execute("""SELECT TOP (1) STATUS, OCCUR_DATE, ALARM_CODE FROM dbo.TDAM0002
                WHERE MACHINE_CODE = ? AND OCCUR_DATE < ? ORDER BY OCCUR_DATE DESC, STATUS, ALARM_CODE""",
                (machine_code, end))
            latest = cursor.fetchone()
            return {"test_data": True, "work_date": CMS_TEST_DATE.isoformat(),
                    "work_date_from": (CMS_TEST_DATE - timedelta(days=7)).isoformat(),
                    "machine_code": machine_code, "machine_name": machine[0],
                    "window_start": start.isoformat(), "window_end_exclusive": end.isoformat(),
                    "history_rows": history_rows, "alarm_events": total_events,
                    "alarm_limit": 5, "recent_events_per_alarm": 3,
                    "requested_codes": list(requested_codes),
                    "latest_record_before_cutoff": {"status": latest[0], "occurred_at": latest[1].isoformat(),
                                                    "alarm_code": latest[2]} if latest else None,
                    "alarms": alarms}
        finally:
            cursor.close()


async def engineer_chunks(service, machine_code, question=""):
    requested = alarm_codes(question)
    snapshot = await asyncio.to_thread(load_engineer_snapshot, machine_code, requested)
    summary = {key: value for key, value in snapshot.items() if key != "alarms"}
    chunks = [{"index": 1, "document": json.dumps(summary, ensure_ascii=False), "metadata": {
        "source_doc_name": "CMS 테스트 기간 집계", "source_kind": "cms", "machine_code": machine_code}}]
    for alarm in snapshot["alarms"]:
        chunks.append({"index": len(chunks) + 1, "document": json.dumps(alarm, ensure_ascii=False), "metadata": {
            "source_doc_name": f"CMS 알람 {alarm['code'] or '코드 미기록'}", "source_kind": "cms",
            "machine_code": machine_code}})
    codes = list(dict.fromkeys([*requested, *[a["code"] for a in snapshot["alarms"]
                                           if a["code"] and a["code"].strip() != "-"]]))[:5]
    documents = build_doc_to_machine_index({machine_code: service.config.machines.get(machine_code, {})})
    # At most one matching excerpt per alarm, five excerpts total. No-history questions still search manuals.
    for code in codes or [None]:
        query = f"{code or ''} 알람 의미 원인 점검 조치 {question}"
        result = await asyncio.to_thread(lambda: service._get_retriever("rag").search(
            query=query, machine_code=machine_code, top_k=5))
        for item in result.items:
            source = item.metadata.get("source_doc_name", "")
            if (not source or source not in documents or machine_code not in _resolve_machine_code(source, documents)
                    or item.metadata.get("container_type") == "ladder" or not item.text.strip()
                    or (code and not contains_code(item.text, code))):
                continue
            # Keep the matching code in the bounded excerpt, including when it occurs late in a chunk.
            position = re.search(r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])", item.text, re.I).start() if code else 0
            text = item.text[max(0, position - 300):max(0, position - 300) + 1800]
            existing = next((chunk for chunk in chunks
                             if chunk["metadata"].get("source_kind") == "manual"
                             and chunk["metadata"].get("source_doc_name") == source
                             and chunk["metadata"].get("page_range") == item.metadata.get("page_range")
                             and chunk["document"] == text), None)
            if existing:
                if code and code not in existing["metadata"]["matched_alarm_codes"]:
                    existing["metadata"]["matched_alarm_codes"].append(code)
                break
            chunks.append({"index": len(chunks) + 1, "document": text, "metadata": {
                **item.metadata, "source_kind": "manual", "matched_alarm_code": code,
                "matched_alarm_codes": [code] if code else []}})
            break
    return snapshot, chunks
