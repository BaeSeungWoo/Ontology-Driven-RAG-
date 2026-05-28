from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

# 블록 단위 구분자
NETWORK_START_RE = re.compile(r"^(N\d{5}):\s*(.*)$")

def _read_text_with_fallback(txt_path: Path) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return txt_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return txt_path.read_text(encoding="utf-8", errors="replace")

def process_document(txt_path: str | Path) -> list[dict[str, Any]]:
    """
    TXT(매크로/래더/명령 블록) 파일을
    N00001: 단위 블록으로 분리해서 chunk dict 리스트로 반환.
    """
    txt_path = Path(txt_path)
    raw_text = _read_text_with_fallback(txt_path)

    lines = raw_text.splitlines()

    chunks: list[dict[str, Any]] = []
    current_block_id: str | None = None
    current_header: str = ""
    current_lines: list[str] = []
    
    def flush_block() -> None:
        nonlocal current_block_id, current_header, current_lines
        if current_block_id is None:
            return

        block_text = "\n".join(current_lines).strip()
        if not block_text:
            current_block_id = None
            current_header = ""
            current_lines = []
            return

        chunks.append(
            {
                "chunk_id": f"{txt_path.stem}_{current_block_id}",
                "text": block_text,
                "metadata": {
                    "source": {"doc_name": txt_path.stem},
                    "section": {
                        "title": None,
                        "level": None
                    },
                    "pages": {"range": "1-1"},
                    "container": {
                        "type": "texts",
                        "asset_path": "",
                    },
                },
            }
        )

        current_block_id = None
        current_header = ""
        current_lines = []

    for line in lines:
        stripped = line.rstrip("\n")

        # 새 블록 시작: N00001:
        match = NETWORK_START_RE.match(stripped.strip())
        if match:
            flush_block()
            current_block_id = match.group(1)
            current_header = stripped.strip()
            current_lines = [stripped]
            continue

        # 블록 밖의 헤더/서문 처리
        if current_block_id is None:
            if stripped.strip():
                current_block_id = "PREFACE"
                current_header = "PREFACE"
                current_lines = [stripped]
            continue

        current_lines.append(stripped)

    flush_block()
    return chunks

def save_jsonl(chunks: list[dict[str, Any]], output_path: str | Path) -> None:
    """생성된 chunk 목록을 JSONL 파일로 저장한다.

    Args:
        chunks (list[dict[str, Any]]): 저장할 chunk 목록.
        output_path (str | Path): 출력 JSONL 파일 경로.

    Returns:
        None
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")