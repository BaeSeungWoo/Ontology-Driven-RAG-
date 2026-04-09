from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz


TOC_KEYWORDS = ("contents", "table of contents", "index", "toc")

def get_toc_map(pdf_path: str | Path, output_txt_path: str | Path | None = None) -> dict[int, str]:
    """fitz(pymupdf) 라이브러리를 사용하여 원문 PDF의 목차 정보를 반환
    
    원문에서 목차 정보를 가져와 계층 구조(Path)를 생성하며, 각 페이지 번호가 
    어느 목차 범위에 속하는지 계산하여 딕셔너리 형태로 구성

    Args:
        pdf_path (str): 원문 PDF 경로
        output_txt_path (str | Path | None, Optional): 목차 정보를 txt 파일로 저장할 경로
            기본 값은 None을 사용, 저장하지 않는다

    Returns:
        dict[int, str]: 페이지 번호(int)를 키로, 해당 페이지의 목차 경로(str)를 값으로 갖는 딕셔너리.
    
    Examples:
        >>> # PDF 목차가 [1, '개요', 1], [2, '상세내용', 3] 구조일 때
        >>> toc_map = get_toc_map("manual.pdf")
        >>> print(toc_map[1])
            '개요 (Level 1)'
        >>> print(toc_map[3])
            '개요 > 상세내용 (Level 2)'
        >>> # 텍스트 리포트와 함께 저장 시
        >>> get_toc_map("manual.pdf", output_txt_path="toc_report.txt")
    """
    
    pdf_path = Path(pdf_path)
    doc = fitz.open(pdf_path)
    toc = doc.get_toc()

    if not toc:
        print("No TOC entries found.")
        return {}

    total_pages = doc.page_count
    current_path = [""] * 7
    toc_map: dict[int, str] = {}

    for i, (level, title, start_page) in enumerate(toc):
        if level >= len(current_path):
            current_path.extend([""] * (level - len(current_path) + 1))

        current_path[level] = title
        for j in range(level + 1, len(current_path)):
            current_path[j] = ""

        end_page = toc[i + 1][2] if i + 1 < len(toc) else total_pages + 1
        path_str = " > ".join([t for t in current_path if t])
        full_display_text = f"{path_str} (Level {level})"

        for page_no in range(start_page, end_page):
            if 1 <= page_no <= total_pages:
                toc_map[page_no] = full_display_text

    if output_txt_path is not None:
        output_txt_path = Path(output_txt_path)
        with output_txt_path.open("w", encoding="utf-8") as f:
            f.write(f"{pdf_path.name} TOC Report\n")
            f.write("=" * 60 + "\n\n")

            last_added_path = ""
            for page_no in range(1, total_pages + 1):
                current_entry = toc_map.get(page_no)
                if current_entry and current_entry != last_added_path:
                    f.write(f"[Page {page_no:03d}] {current_entry}\n")
                    last_added_path = current_entry

    return toc_map


def parse_toc_entry(entry: str | None) -> tuple[str | None, str | None]:
    """목차 문자열에서 제목과 계층 레벨을 분리하여 추출

    '제목 (Level N)' 형식의 문자열을 분석하여, 제목 부분과 숫자 N을 각각 분리

    Args:
        entry (str | None): 목차 문자열 (예: "소개 > 설치 방법 (Level 2)")

    Returns:
        tuple[str | None, str | None]: (제목, 레벨) 형태의 튜플
    """
    if not entry:
        return None, None
    match = re.search(r"\(Level\s+(\d+)\)\s*$", entry)
    if not match:
        return entry.strip(), None
    return entry[: match.start()].strip(), match.group(1)


def score_toc_page(page: fitz.Page, max_scan_words: int = 250) -> int:
    """PDF 페이지의 텍스트 패턴을 분석하여 목차 페이지일 가능성을 점수로 반환
    
    네 가지 기준(키워드, 점선 패턴, 항목 구조, 단어 밀도)을 바탕으로 점수를 합산하며,
    점수가 높을 수록 해당 페이지가 목차일 확률을 의미함.

    Args:
        page (fitz.Page): 분석할 페이지 객체
        max_scan_words (int, Optional): 목차 페이지로 간주 할 최대 단어 수,
            기본값 250

    Returns:
        int: 계산된 목차 점수 (최소 0점 ~ 최소 13점)
    """
    text = page.get_text("text")
    words = page.get_text("words")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head_text = "\n".join(lines[:20]).lower()

    score = 0
    # 1. 키워드 검사: (TOC_KEYWORDS는 외부 정의 필요)
    if any(keyword in head_text for keyword in TOC_KEYWORDS):
        score += 5

    # 2. 리더 라인(점선) 검사: 제목..........12
    leader_lines = sum(
        1
        for line in lines
        if re.search(r"\.{4,}\s*[A-Za-z0-9ivxlcdm-]+\s*$", line, re.IGNORECASE)
    )
    if leader_lines >= 3:
        score += 4

    # 3. 번호가 매겨진 항목 구조 검사: 1.1 개요 5
    numbered_entry_lines = sum(
        1
        for line in lines
        if re.search(r"^\s*(\d+(\.\d+)*)?\s*.+\s+([A-Za-z]?\d+|[ivxlcdm]+)\s*$", line, re.IGNORECASE)
    )
    if numbered_entry_lines >= 5:
        score += 3

    # 4. 적절한 텍스트 양 검사
    if 30 <= len(words) <= max_scan_words:
        score += 1

    return score


def detect_toc_pages(pdf_path: str | Path, scan_pages: int, min_score: int) -> set[int]:
    """원문 PDF에서 목차에 해당 하는 페이지들을 추출

    PDF 1페이지 부터 `scan_pages`에 해당하는 범위까지 확인
    페이지에서 `score_toc_page`를 통해 반환하는 점수가 `min_score` 보다 높을 경우 목차 페이지로 선정함.

    Args:
        pdf_path (str | Path): 원문 PDF 경로
        scan_pages (int): 1페이지 부터 확인할 페이지의 범위
            기본 값은 프로젝트 설정 상 `TOC_SCAN_PAGES` 사용
        min_score (int): 목차 선정 기준 점수
            기본 값은 프로젝트 설정 상 `TOC_MIN_SCORE` 사용

    Returns:
        set[int]: 목차로 선정된 페이지 번호의 집합

    Examples:
        >>> # 1, 2페이지가 목차 점수 기준을 통과했을 때
        >>> detect_toc_pages("manual.pdf", scan_pages=10, min_score=70)
            {1, 2}
        >>> # 목차 페이지를 찾지 못했을 때
        >>> detect_toc_pages("no_toc_file.pdf")
            set()        
    """
    toc_pages: set[int] = set()
    with fitz.open(pdf_path) as doc:
        limit = min(scan_pages, doc.page_count)
        for page_index in range(limit):
            if score_toc_page(doc[page_index]) >= min_score:
                toc_pages.add(page_index + 1)
    return toc_pages


def get_section_from_toc(pages: list[int], toc_map: dict[int, str]) -> dict[str, Any]:
    """페이지 번호 목록을 바탕으로 해당 요소가 속한 문서 섹션 정보 추출

    요소가 위치한 각 페이지를 `toc_map`에서 조회 후, 가장 먼저 매칭되는
    목차 엔트리의 제목, 계층 레벨을 반환

    Args:
        pages (list[int]): 페이지 번호 리스트
        toc_map (dict[int, str]): 목차 정보

    Returns:
        dict [str, Any]: 섹션 정보를 담은 dict
    
    """
    for page_no in pages:
        toc_entry = toc_map.get(page_no)
        if toc_entry:
            title, level = parse_toc_entry(toc_entry)
            return {"title": title, "level": level, "raw": toc_entry}
    return {"title": None, "level": None, "raw": None}


def filter_toc_pages(pages: list[int], toc_pages: set[int] | None) -> list[int]:
    """원래 페이지 순서는 유지하면서, 목차로 판단한 페이지를 제외.
    
    Args:
        pages (list[int]): 전체 페이지 번호 리스트
        toc_pages (set[int]): 목차로 판별된 페이지 번호 리스트

    Returns:
        list[int]: 목차 페이지가 제거된 페이지 번호 리스트    
    """
    if not toc_pages:
        return pages
    return [page for page in pages if page not in toc_pages]