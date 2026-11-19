"""Server-owned answer generation. Stream subscribers never own the model task."""
import asyncio
from contextlib import aclosing
import json
import logging
import re
from time import time
from uuid import uuid4

from fastapi import HTTPException

from app.database import database

active = {}


class AnswerJob:
    def __init__(self, session_id, message_id, mode, persona):
        self.session_id = session_id
        self.message_id = message_id
        self.content = ""
        self.status = "running"
        self.started = int(time() * 1000)
        self.metadata = {"generation_id": uuid4().hex, "persona_type": persona}
        self.mode = mode
        if mode == "electrical":
            self.metadata.update(progress_started_at=self.started, progress_history=[])
        self.changed = asyncio.Event()
        self.task = None
        self.stopping = False

    def notify(self):
        self.changed.set()
        self.changed = asyncio.Event()

    def snapshot(self):
        return {"message_id": self.message_id, "content": self.content, "metadata": self.metadata,
                "status": self.status}

    async def stream(self):
        while True:
            changed = self.changed
            yield json.dumps(self.snapshot(), ensure_ascii=False) + "\n"
            if self.status != "running":
                return
            try:
                await asyncio.wait_for(changed.wait(), timeout=10)
            except TimeoutError:
                pass
            await asyncio.sleep(0.08)

    def stop(self):
        if self.task and not self.stopping and self.status == "running":
            self.stopping = True
            self.task.cancel()

    async def run(self, events):
        try:
            async with aclosing(events) as stream:
                async for event in stream:
                    value = event["data"]
                    if event["type"] == "metadata":
                        self.metadata.update(value)
                    elif event["type"] == "token":
                        self.content += value
                    elif event["type"] == "progress":
                        entry = dict(value) if isinstance(value, dict) else {"message": value}
                        entry["at"] = int(time() * 1000)
                        history = self.metadata.setdefault("progress_history", [])
                        if history and history[-1]["message"] == entry["message"]:
                            history[-1].update(entry)
                        else:
                            history.append(entry)
                        self.metadata.update(progress_message=entry["message"], progress_updated_at=entry["at"])
                    self.notify()
            if not self.content.strip():
                raise RuntimeError("모델에서 답변을 받지 못했습니다.")
            status = "completed"
        except asyncio.CancelledError:
            status = "cancelled"
            self.content = self.content or "사용자가 답변 생성을 중단했습니다."
        except Exception as exc:
            logging.exception("Answer generation failed for message %s", self.message_id)
            status = "failed"
            self.content = f"요청 실패: {exc}"
        # Once generation ends, cancellation must not interrupt the DB commit.
        self.stopping = True
        now = int(time() * 1000)
        self.metadata.update(generation_status=status, elapsed_ms=now - self.started)
        if status != "completed":
            self.metadata["request_failed"] = True
        if self.mode == "electrical":
            self.metadata["progress_finished_at"] = now
        if self.metadata.get("chunks"):
            used = {int(i) for i in re.findall(r"\[chunk:(\d+)\]", self.content, re.I)}
            self.metadata["used_chunks"] = [c for c in self.metadata["chunks"] if c.get("index") in used]
        for attempt in range(3):
            try:
                await asyncio.to_thread(database.updateChatMessage, self.message_id, self.content,
                                        json.dumps(self.metadata, ensure_ascii=False))
                break
            except Exception:
                logging.exception("Could not save answer %s", self.message_id)
                if attempt == 2:
                    status = "save_failed"
                else:
                    await asyncio.sleep(attempt + 1)
        self.status = status
        active.pop(self.session_id, None)
        self.notify()


def start(session_id, question, mode, persona, retry_id, events_factory):
    if session_id in active:
        raise HTTPException(409, "이 대화에서 답변을 생성하고 있습니다.")
    if retry_id is None:
        user_id, message_id = database.createAnswerTurn(session_id, question)
    else:
        rows = database.getChatMessagesBySession(session_id)
        if (len(rows) < 2 or rows[-1][0] != retry_id or rows[-1][2] != "assistant"
                or rows[-2][2] != "user" or rows[-2][3] != question
                or (rows[-1][3] and not json.loads(rows[-1][8] or "{}").get("request_failed"))):
            raise HTTPException(409, "마지막 중단된 답변만 다시 생성할 수 있습니다.")
        user_id, message_id = rows[-2][0], retry_id
    job = AnswerJob(session_id, message_id, mode, persona)
    active[session_id] = job
    job.task = asyncio.create_task(job.run(events_factory()))
    return {"user_message_id": user_id, **job.snapshot()}
