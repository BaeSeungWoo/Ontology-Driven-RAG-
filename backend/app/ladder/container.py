"""FANUC LADDER-III .LAD 컨테이너(ZIP) 접근.

.LAD 파일은 일반 ZIP이며 각 멤버명 뒤에 LADDER-III가 붙인 16자리 16진 접미사가 있다.
예) 'LEVEL1.#LAc21ccd5001dd51b9' -> 논리 이름 'LEVEL1.#LA'

C:\\workspace\\repos\\2026\\Fanuc_LAD_Decode\\fanuc_lad\\container.py를 그대로 포팅하되,
업로드 파일을 디스크에 저장하지 않고 메모리에서 바로 파싱하기 위해 경로 대신
파일류 객체(BytesIO)를 받도록 생성자만 바꿨다.
"""
from __future__ import annotations

import re
import zipfile
from typing import BinaryIO, Dict, List, Optional, Tuple, Union

_SUFFIX_RE = re.compile(r"^(?P<base>.+?)(?P<suffix>[0-9a-f]{16})$")
LADDER_MEMBER_RE = re.compile(r"^(?:LEVEL(?P<level>\d+)|P(?P<sub>\d+))\.#LA$", re.IGNORECASE)


def logical_name(member_name: str) -> str:
    """멤버명에서 16자리 16진 접미사를 제거한 논리 이름을 돌려준다."""
    m = _SUFFIX_RE.match(member_name)
    return m.group("base") if m else member_name


def _ladder_sort_key(name: str) -> Tuple[int, int]:
    m = LADDER_MEMBER_RE.match(name)
    if not m:
        return (9, 0)
    if m.group("level") is not None:
        return (0, int(m.group("level")))
    return (1, int(m.group("sub")))


class LadFile:
    """.LAD ZIP 컨테이너. 논리 이름으로 멤버를 읽는다."""

    def __init__(self, file_obj: Union[str, BinaryIO]):
        self._zip = zipfile.ZipFile(file_obj)
        self.members: Dict[str, zipfile.ZipInfo] = {}
        for info in self._zip.infolist():
            if info.is_dir():
                continue
            self.members[logical_name(info.filename)] = info

    def __enter__(self) -> "LadFile":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._zip.close()

    def has(self, name: str) -> bool:
        return name in self.members

    def read(self, name: str) -> bytes:
        return self._zip.read(self.members[name])

    def read_optional(self, name: str) -> Optional[bytes]:
        return self.read(name) if self.has(name) else None

    def ladder_member_names(self) -> List[str]:
        """LEVEL1, LEVEL2, LEVEL3, P1, P2 ... 순서로 정렬된 래더 멤버 이름."""
        names = [n for n in self.members if LADDER_MEMBER_RE.match(n)]
        return sorted(names, key=_ladder_sort_key)

    def member_table(self) -> List[Tuple[str, str, int]]:
        """(논리 이름, 원래 이름, 압축 해제 크기) 목록."""
        return [(logical, info.filename, info.file_size) for logical, info in self.members.items()]
