"""Read-only PMC access to the explicitly configured test machine."""
import base64
import binascii
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from app.ladder.document import load_lad

ladderRouter = APIRouter(prefix="/api/ladder", tags=["ladder"])
ADDRESS = re.compile(r"([GFYXRAKTCD])([0-9]{1,5})\.([0-7])")


def test_machine_code():
    code = os.getenv("LADDER_TEST_MACHINE_CODE", "M019")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", code):
        raise HTTPException(503, "테스트 장비 코드 설정이 올바르지 않습니다.")
    return code


@ladderRouter.get("/test-document")
def ladder_document():
    code = test_machine_code()
    path = Path(__file__).resolve().parents[2] / "data" / "ladder" / f"{code}.LAD"
    try:
        doc = load_lad(str(path))
        if not any(net["outputs"] for program in doc["ladders"] for net in program["nets"]):
            raise ValueError("표시할 회로가 없는 래더 파일입니다.")
        doc["meta"].update(machine_code=code, filename=path.name)
        return doc
    except OSError as exc:
        raise HTTPException(404, "테스트 장비의 래더 파일을 찾을 수 없습니다.") from exc
    except (ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
        raise HTTPException(422, str(exc) or "래더 파일을 읽지 못했습니다.") from exc


class SignalRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=128)

    @field_validator("addresses")
    @classmethod
    def validate_addresses(cls, addresses):
        result = []
        for address in addresses:
            match = ADDRESS.fullmatch(address.upper())
            if not match or int(match[2]) > 32767:
                raise ValueError("PMC 비트 주소 형식이 잘못되었습니다. 예: X8.4")
            result.append(f"{match[1]}{int(match[2])}.{match[3]}")
        return list(dict.fromkeys(result))


def address_ranges(addresses):
    """요청된 연속 바이트만 묶어 불필요한 주소 구간을 읽지 않는다."""
    by_area = {}
    for address in addresses:
        match = ADDRESS.fullmatch(address)
        by_area.setdefault(match[1], set()).add(int(match[2]))
    for area, numbers in by_area.items():
        start = end = None
        for number in sorted(numbers):
            if start is not None and (number != end + 1 or number - start >= 200):
                yield area, start, end
                start = None
            if start is None:
                start = number
            end = number
        yield area, start, end


def decode_range(payload, area, start, end):
    # 에이전트의 byte[]는 Base64로 전달된다. 주소와 길이를 확인한 뒤 비트로 분해한다.
    if (payload.get("pmcType"), payload.get("start"), payload.get("end")) != (area, start, end):
        raise ValueError("PMC 응답 주소가 요청과 다릅니다.")
    raw = payload.get("data")
    if isinstance(raw, str):
        data = base64.b64decode(raw, validate=True)
    elif isinstance(raw, list) and all(type(value) is int and 0 <= value <= 255 for value in raw):
        data = bytes(raw)
    else:
        raise ValueError("PMC 응답 데이터 형식이 잘못되었습니다.")
    if len(data) != end - start + 1:
        raise ValueError("PMC 응답 길이가 요청과 다릅니다.")
    return data


@ladderRouter.post("/test-signals")
async def test_signals(request: SignalRequest):
    # 앱의 dotenv 로딩 이후 설정을 읽도록 요청 시점에 통신 대상을 결정한다.
    agent_url = os.getenv("LADDER_AGENT_URL", "http://127.0.0.1:5001").rstrip("/")
    machine_code = test_machine_code()
    path = f"/api/agent/fanuc/machines/{machine_code}"
    async with httpx.AsyncClient(base_url=agent_url, timeout=5, trust_env=False) as client:
        try:
            response = await client.get(path)
            response.raise_for_status()
            machine = response.json()
            if machine.get("MachineCode") != machine_code:
                raise ValueError("장비 코드 불일치")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise HTTPException(502, "테스트 에이전트 또는 장비 목록에 연결할 수 없습니다.") from exc

        values, errors = {}, {}
        for area, start, end in address_ranges(request.addresses):
            try:
                response = await client.get(f"{path}/pmc/range", params={"pmcType": area, "start": start, "end": end})
                response.raise_for_status()
                data = decode_range(response.json(), area, start, end)
                for offset, value in enumerate(data):
                    values[(area, start + offset)] = value
            except (httpx.HTTPError, ValueError, AttributeError, binascii.Error):
                for number in range(start, end + 1):
                    errors[(area, number)] = "신호 조회 실패 · 장비 연결 또는 주소 범위를 확인하세요."

    signals = []
    for address in request.addresses:
        match = ADDRESS.fullmatch(address)
        key = (match[1], int(match[2]))
        # 미수신은 OFF(0)와 다르다. null을 유지해 화면에서 통전으로 표시하지 않는다.
        value = (values[key] >> int(match[3])) & 1 if key in values else None
        signals.append({"address": address, "value": value, "error": errors.get(key)})
    return {
        "test_mode": True,
        "machine": {"code": machine_code, "name": machine.get("MachineName", machine_code), "ip": machine.get("MachineIP", "")},
        "read_completed": datetime.now(timezone.utc).isoformat(),
        "signals": signals,
    }
