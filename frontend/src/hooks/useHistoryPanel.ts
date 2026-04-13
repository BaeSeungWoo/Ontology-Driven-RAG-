import { useEffect, useMemo, useRef, useState } from "react";
import type { HistoryItem } from "@/components/chat/history/historyCard";
import {
  getHistoryPagination,
  getHistoryQuestioner,
  getHistoryQuestionerCounts,
} from "@/services/historyApi";
import type { HistoryResponse } from "@/types/historyApi";
import { LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS } from "@/constants/llmOptions";

/**
 * 기능: 질문자 필터 칩 렌더링 옵션 타입
 * 목적: 질문자 key/label/count를 한 구조로 관리
 * In: 질문자 집계 API 결과
 * Out: QuestionerOption 타입 정보
 */
export type QuestionerOption = {
  key: string;
  label: string;
  count: number;
};

const ALL_QUESTIONER_FILTER = "__all__";
const HISTORY_PAGE_SIZE = 5;

/**
 * 기능: 서버 날짜 문자열을 카드 표기용 포맷으로 변환
 * 목적: 이력 카드의 시간 표시 형식을 일관되게 유지
 * In: value(string | undefined)
 * Out: formattedDateTime(string)
 */
function formatDateTime(value: string | undefined): string {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const yy = String(date.getFullYear()).slice(-2);
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yy}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * 기능: 히스토리 API row를 UI 카드 타입으로 정규화
 * 목적: 카드 표시에 필요한 라벨과 세션 동기화에 필요한 원본 메타를 함께 구성한다.
 * In: row(HistoryResponse), selectedSessionId
 * Out: HistoryItem
 */
function toHistoryItem(row: HistoryResponse, selectedSessionId: number | null): HistoryItem {
  const id = Number(row.sessionId);
  const llmModelLabel =
    LLM_MODEL_OPTIONS.find((option) => option.value === row.llmModel)?.label ?? row.llmModel;
  const llmModeLabel =
    LLM_MODE_OPTIONS.find((option) => option.value === row.llmMode)?.label ?? row.llmMode;

  return {
    id,
    title: row.title ?? "제목 없음",
    questioner: row.questioner ?? "-",
    llmModel: row.llmModel ?? "",
    llmMode: row.llmMode ?? "",
    promptNo: Number.isFinite(Number(row.promptNo)) ? Number(row.promptNo) : null,
    llmModelLabel,
    llmModeLabel,
    promptName: row.promptName ?? "-",
    recentAt: formatDateTime(row.updatedAt ?? row.createdAt),
    isActive: selectedSessionId === id,
  };
}

/**
 * 기능: useHistoryPanel 훅 입력 타입
 * 목적: 훅이 필요로 하는 외부 상태를 명확히 정의
 * In: 선택 세션 id, 갱신 트리거 키
 * Out: UseHistoryPanelParams 타입 정보
 */
type UseHistoryPanelParams = {
  selectedSessionId: number | null;
  refreshKey: number;
};

/**
 * 기능: 질문 이력 패널의 데이터 동기화/필터/페이지네이션 상태를 통합 관리
 * 목적: history.tsx는 렌더 중심으로 단순화하고, API/상태 로직은 훅으로 분리
 * In: selectedSessionId, refreshKey
 * Out: 카드 목록, 질문자 필터, 페이지네이션, 스크롤 제어 핸들러
 */
export function useHistoryPanel({ selectedSessionId, refreshKey }: UseHistoryPanelParams) {
  // =========================
  // State
  // =========================
  const [historyItems, setHistoryItems] = useState<HistoryItem[]>([]);
  const [selectedQuestioner, setSelectedQuestioner] = useState<string>(ALL_QUESTIONER_FILTER);
  const [questionerOptions, setQuestionerOptions] = useState<QuestionerOption[]>([
    { key: ALL_QUESTIONER_FILTER, label: "전체", count: 0 },
  ]);

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [totalCount, setTotalCount] = useState<number>(0);

  const [canScrollQuestionerLeft, setCanScrollQuestionerLeft] = useState(false);
  const [canScrollQuestionerRight, setCanScrollQuestionerRight] = useState(false);
  const questionerFilterScrollRef = useRef<HTMLDivElement | null>(null);

  // =========================
  // 함수
  // =========================
  const hasSelectedQuestionerOption = questionerOptions.some(
    (option) => option.key === selectedQuestioner
  );

  const effectiveSelectedQuestioner = hasSelectedQuestionerOption
    ? selectedQuestioner
    : ALL_QUESTIONER_FILTER;

  /**
   * 기능: 질문자 칩 스크롤 화살표 활성 상태를 계산한다.
   * 목적: 이동 불가 방향의 화살표를 비활성화해 UX를 명확히 한다.
   * In: 칩 컨테이너의 scrollLeft/scrollWidth/clientWidth
   * Out: canScrollQuestionerLeft/canScrollQuestionerRight 갱신
   */
  function updateQuestionerScrollButtonState() {
    const container = questionerFilterScrollRef.current;
    if (!container) return;

    const maxScrollLeft = container.scrollWidth - container.clientWidth;
    const currentScrollLeft = container.scrollLeft;

    setCanScrollQuestionerLeft(currentScrollLeft > 0);
    setCanScrollQuestionerRight(currentScrollLeft < maxScrollLeft - 1);
  }

  /**
   * 기능: 질문자 칩 영역을 좌/우로 스크롤한다.
   * 목적: 칩이 많은 경우 버튼으로 필터를 탐색할 수 있게 한다.
   * In: direction("left" | "right")
   * Out: questionerFilterScrollRef의 scrollLeft 변경
   */
  const handleQuestionerFilterScroll = (direction: "left" | "right") => {
    const container = questionerFilterScrollRef.current;
    if (!container) return;

    container.scrollBy({
      left: direction === "left" ? -180 : 180,
      behavior: "smooth",
    });
  };

  /**
   * 기능: 질문자 필터를 변경한다.
   * 목적: 필터 변경 시 항상 1페이지부터 조회되도록 보장한다.
   * In: questionerKey(string)
   * Out: selectedQuestioner/currentPage 상태 갱신
   */
  const handleSelectQuestioner = (questionerKey: string) => {
    if (selectedQuestioner === questionerKey) return;
    setSelectedQuestioner(questionerKey);
    setCurrentPage(1);
  };

  const safeCurrentPage = Math.min(currentPage, totalPages);
  const isHistoryEmpty = historyItems.length === 0;

  const visibleQuestionerOptions = useMemo(() => {
    if (questionerOptions.length === 0) {
      return [{ key: ALL_QUESTIONER_FILTER, label: "전체", count: totalCount }];
    }
    return questionerOptions;
  }, [questionerOptions, totalCount]);

  /**
   * 기능: 이전 페이지로 이동한다.
   * 목적: 현재 페이지를 1 미만으로 내리지 않도록 안전하게 제어한다.
   * In: 이전 버튼 클릭
   * Out: currentPage 감소(최소 1)
   */
  const goPrevPage = () => setCurrentPage((prev) => Math.max(1, prev - 1));

  /**
   * 기능: 다음 페이지로 이동한다.
   * 목적: 현재 페이지를 totalPages 초과로 올리지 않도록 제어한다.
   * In: 다음 버튼 클릭
   * Out: currentPage 증가(최대 totalPages)
   */
  const goNextPage = () => setCurrentPage((prev) => Math.min(totalPages, prev + 1));

  /**
   * 기능: 지정한 페이지로 이동한다.
   * 목적: 페이지 번호 버튼 클릭 시 목표 페이지로 즉시 전환한다.
   * In: page(number)
   * Out: currentPage = page
   */
  const goPage = (page: number) => setCurrentPage(page);

  /**
   * 기능: 질문자 필터를 전체로 초기화한다.
   * 목적: 새 질문 시작 시 필터 컨텍스트를 기본값으로 복원한다.
   * In: 새 질문/초기화 이벤트
   * Out: selectedQuestioner=전체, currentPage=1
   */
  const resetQuestionerFilter = () => {
    setSelectedQuestioner(ALL_QUESTIONER_FILTER);
    setCurrentPage(1);
  };

  // =========================
  // useEffect
  // =========================
  /**
   * 기능: 질문자별 이력 건수를 조회한다.
   * 목적: 상단 필터 칩(질문자 + count)을 최신 상태로 유지한다.
   * In: refreshKey 변경
   * Out: questionerOptions 갱신
   */
  useEffect(() => {
    const fetchQuestionerOptions = async () => {
      try {
        const counts = await getHistoryQuestionerCounts();
        const normalized = counts
          .map((item) => ({
            key: item.questioner?.trim() || "-",
            label: item.questioner?.trim() || "-",
            count: Number(item.count) || 0,
          }))
          .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, "ko"));

        const allCount = normalized.reduce((sum, item) => sum + item.count, 0);
        setQuestionerOptions([
          { key: ALL_QUESTIONER_FILTER, label: "전체", count: allCount },
          ...normalized,
        ]);
      } catch (error) {
        console.error("getHistoryQuestionerCounts failed:", error);
      }
    };

    void fetchQuestionerOptions();
  }, [refreshKey]);

  /**
   * 기능: 현재 필터/페이지 기준으로 이력 목록을 조회한다.
   * 목적: 서버 페이지네이션 결과를 카드 목록/메타 상태에 반영한다.
   * In: effectiveSelectedQuestioner/currentPage/selectedSessionId/refreshKey 변경
   * Out: historyItems/totalCount/totalPages/currentPage 보정
   */
  useEffect(() => {
    let isMounted = true;

    const fetchHistoryPage = async () => {
      try {
        const response =
          effectiveSelectedQuestioner === ALL_QUESTIONER_FILTER
            ? await getHistoryPagination({ page: currentPage, page_size: HISTORY_PAGE_SIZE })
            : await getHistoryQuestioner({
                questioner: effectiveSelectedQuestioner,
                page: currentPage,
                page_size: HISTORY_PAGE_SIZE,
              });

        if (!isMounted) return;

        const rows = response.rows ?? [];
        const nextTotalCount = Number(response.total_count) || 0;
        const nextTotalPages = Math.max(1, Number(response.total_pages) || 1);

        setHistoryItems(rows.map((row) => toHistoryItem(row, selectedSessionId)));
        setTotalCount(nextTotalCount);
        setTotalPages(nextTotalPages);

        if (currentPage > nextTotalPages) {
          setCurrentPage(nextTotalPages);
        }
      } catch (error) {
        console.error("getHistoryPagination/getHistoryQuestioner failed:", error);
        if (isMounted) {
          setHistoryItems([]);
          setTotalCount(0);
          setTotalPages(1);
        }
      }
    };

    void fetchHistoryPage();

    return () => {
      isMounted = false;
    };
  }, [effectiveSelectedQuestioner, currentPage, selectedSessionId, refreshKey]);

  /**
   * 기능: 질문자 칩 렌더 직후 스크롤 버튼 상태를 동기화한다.
   * 목적: DOM 크기 확정 이후 좌/우 화살표 활성화를 정확히 맞춘다.
   * In: questionerOptions 변경
   * Out: updateQuestionerScrollButtonState 실행
   */
  useEffect(() => {
    const timer = window.setTimeout(() => {
      updateQuestionerScrollButtonState();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [questionerOptions]);

  // =========================
  // Render(return)
  // =========================
  return {
    canScrollQuestionerLeft,
    canScrollQuestionerRight,
    currentPage: safeCurrentPage,
    effectiveSelectedQuestioner,
    historyItems,
    isHistoryEmpty,
    questionerFilterScrollRef,
    totalPages,
    updateQuestionerScrollButtonState,
    visibleQuestionerOptions,
    handleQuestionerFilterScroll,
    handleSelectQuestioner,
    resetQuestionerFilter,
    goPrevPage,
    goNextPage,
    goPage,
  };
}


