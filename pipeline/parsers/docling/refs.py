from __future__ import annotations

from typing import Any


def build_indexes(data: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    """Docling 주요 노드를 self_ref 기준 조회 인덱스로 변환
    
    ``texts``, ``groups``, ``tables``, ``pictures`` 컬렉션을 대상으로
    각 노드의 ``self_ref`` 를 키로 하는 조회용 딕셔너리를 생성

    Args:
        data (dict[str, Any]): Docling JSON 전체 데이터.

    Returns:
        dict[str, dict[str, dict[str, Any]]]: 컬렉션별 self_ref 조회 인덱스.
    """
    indexes: dict[str, dict[str, dict[str, Any]]] = {}
    for key in ("texts", "groups", "tables", "pictures"):
        indexes[key] = {}
        for item in data.get(key, []):
            self_ref = item.get("self_ref")
            if self_ref:
                indexes[key][self_ref] = item
    return indexes


def ref_kind(ref: str | None) -> str | None:
    """Docling 참조 경로에 따라 해당 데이터의 타입을 생성
    
    Args:
        ref (str | None): Docling 참조 경로 문자열

    Returns:
        str | None: 분류된 타입
    """
    if not ref:
        return None
    if ref == "#/body":
        return "body"
    if ref == "#/furniture":
        return "furniture"
    if ref.startswith("#/texts/"):
        return "texts"
    if ref.startswith("#/groups/"):
        return "groups"
    if ref.startswith("#/tables/"):
        return "tables"
    if ref.startswith("#/pictures/"):
        return "pictures"
    return None


def ref_id(ref: str | None) -> str | None:
    """Docling 참조 경로에서 마지막 식별자 세그먼트를 추출하여 반환
    
    /로 구분된 경로 문자열을 분리하여 맨 뒤에 위치한 명칭을 찾음.
    주로 전체 경로에서 특정 요소의 고유 ID만 뽑아낼 때 사용

    Args:
        ref (str | None): 분석할 Docling 참조 경로 문자열 (예: "#/body/tables/0").

    Returns:
        str | None: 추출된 마지막 식별자. 입력값이 None이면 None을 반환합니다.

    Examples:
        >>> ref_id("#/content/items/123")
            '123'
        >>> ref_id("documents/assets/image_01")
            'image_01'
        >>> ref_id(None)
            None
    """
    if not ref:
        return None
    return ref.split("/")[-1]


def resolve_ref(ref: str | None, indexes: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any] | None:
    """Docling 참조 문자열을 통해 해당 노드의 실제 데이터를 반환
    
    Args:
        ref (str | None): 조회할 노드의 고유 참조 주소
        indexes (dict[str, dict[str, Any]]): 인덱스 저장소

    Returns:
        dict[str, Any] | None: 찾은 노드의 데이터 객체
    """
    kind = ref_kind(ref)
    if kind in indexes and ref:
        return indexes[kind].get(ref)
    return None

def collect_refs(ref: str, indexes: dict[str, dict[str, dict]], out: list[str]) -> None:
    """그룹 ref를 재귀적으로 펼쳐 최종 leaf ref들을 수집한다.

    입력 ref가 ``groups`` 타입이면 해당 그룹의 자식 ref들을 재귀적으로 순회하고,
    그룹이 아닌 ref면 그대로 결과 리스트에 추가

    Args:
        ref (str): 시작할 Docling ref 문자열.
        indexes (dict[str, dict[str, dict]]): ``build_indexes`` 로 생성한 ref 조회 인덱스.
        out (list[str]): 수집된 leaf ref를 추가할 출력 리스트.

    Returns:
        None: 결과는 ``out`` 리스트에 직접 누적
    """
    kind = ref_kind(ref)
    if kind == "groups":
        group = indexes["groups"].get(ref)
        if not group:
            return
        for child in group.get("children", []):
            child_ref = child.get("$ref")
            if child_ref:
                collect_refs(child_ref, indexes, out)
    else:
        out.append(ref)
