import { useState } from "react";
import {
  ClipboardClock,
  ChevronDown,
  ChevronFirst,
  ChevronLast,
  ChevronLeft,
  ChevronRight,
  PanelRightClose,
  PanelRightOpen,
  Search,
  SquarePen,
  UsersRound,
} from "lucide-react";

import { useHistoryPanel } from "@/hooks/useHistoryPanel";
import { deleteHistorySession } from "@/services/historyApi";

import HistoryCard from "./historyCard";
import type { HistoryItem } from "./historyCard";
import styles from "./history.module.css";

type HistoryProps = {
  selectedSessionId: number | null;
  onSelectSession: (sessionId: number, sessionMeta?: HistorySessionMeta) => void;
  onStartNewChat?: () => void;
  onDeleteSession?: (sessionId: number) => void;
  onHistoryRefresh?: () => void;
  refreshKey?: number;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
};

type HistorySessionMeta = Pick<
  HistoryItem,
  "questioner" | "llmModel" | "llmMode" | "promptNo" | "promptName"
>;

type PaginationItem = number | "ellipsis-left" | "ellipsis-right";

const OPTION_TEXT_MAX = 18;

function formatQuestionerOptionLabel(label: string, count: number): string {
  const countToken = `[${count}]`;
  const reservedLength = countToken.length + 1; // 공백 1칸 포함
  const availableLabelLength = Math.max(4, OPTION_TEXT_MAX - reservedLength);
  const normalized = label.trim();
  const shortLabel =
    normalized.length > availableLabelLength
      ? `${normalized.slice(0, Math.max(1, availableLabelLength - 1))}…`
      : normalized;

  return `${shortLabel} ${countToken}`;
}

export default function History({
  selectedSessionId,
  onSelectSession,
  onStartNewChat,
  onDeleteSession,
  onHistoryRefresh,
  refreshKey = 0,
  isCollapsed = false,
  onToggleCollapse,
}: HistoryProps) {
  // 내부 state
  // 기능/목적: 새 질문 시작 전 확인 모달의 열림 상태를 관리한다.
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const {
    currentPage,
    effectiveSelectedQuestioner,
    goFirstPage,
    goNextPage,
    goLastPage,
    goPage,
    goPrevPage,
    handleSelectQuestioner,
    questionerSearchKeyword,
    handleChangeQuestionerSearchKeyword,
    applyQuestionerSearchKeyword,
    clearQuestionerSearchKeyword,
    historyItems,
    isHistoryEmpty,
    totalPages,
    visibleQuestionerOptions,
    resetQuestionerFilter,
  } = useHistoryPanel({
    selectedSessionId,
    refreshKey,
  });

  // 함수: 새 질문
  // 기능/목적: 현재 화면의 대화 상태를 비우기 전 확인 과정을 거친다.
  // Out: 질문자 필터 초기화, 상위 Chat의 새 세션 초기화 호출
  const handleOpenConfirm = () => {
    setIsConfirmOpen(true);
  };

  const handleConfirmNewChat = () => {
    setIsConfirmOpen(false);
    resetQuestionerFilter();
    onStartNewChat?.();
  };

  // 함수: 세션 선택
  // 기능/목적: 선택한 이력 카드의 세션 id와 설정 메타를 상위 Chat에 전달한다.
  // In: sessionId / Out: onSelectSession 호출
  const handleSelectChat = (sessionId: number) => {
    const matchedItem = historyItems.find((item) => item.id === sessionId);

    onSelectSession(
      sessionId,
      matchedItem
        ? {
            questioner: matchedItem.questioner,
            llmModel: matchedItem.llmModel,
            llmMode: matchedItem.llmMode,
            promptNo: matchedItem.promptNo,
            promptName: matchedItem.promptName,
          }
        : undefined
    );
  };

  const handleDeleteChat = async (sessionId: number) => {
    await deleteHistorySession(sessionId);
    onDeleteSession?.(sessionId);
    onHistoryRefresh?.();
  };

  // 함수: 페이지네이션
  // 기능/목적: 전체 페이지 수와 현재 페이지를 기반으로 표시할 페이지 버튼을 계산한다.
  // Out: 숫자 페이지와 말줄임 토큰 배열
  const getPaginationItems = (): PaginationItem[] => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }

    if (currentPage <= 4) {
      return [1, 2, 3, 4, 5, "ellipsis-right", totalPages];
    }

    if (currentPage >= totalPages - 3) {
      return [
        1,
        "ellipsis-left",
        totalPages - 4,
        totalPages - 3,
        totalPages - 2,
        totalPages - 1,
        totalPages,
      ];
    }

    return [
      1,
      "ellipsis-left",
      currentPage - 1,
      currentPage,
      currentPage + 1,
      "ellipsis-right",
      totalPages,
    ];
  };

  const paginationItems = getPaginationItems();
  const rootClassName = `${styles.historyRoot} ${
    isCollapsed ? styles.historyRootCollapsed : ""
  }`;

  // render
  return (
    <div className={rootClassName}>
      <div className={styles.headerRow}>
        <div className={styles.headerTitleGroup}>
          <button
            type="button"
            className={styles.panelToggleButton}
            onClick={onToggleCollapse}
            aria-label={isCollapsed ? "오른쪽 영역 펼치기" : "오른쪽 영역 접기"}
            title={isCollapsed ? "오른쪽 영역 펼치기" : "오른쪽 영역 접기"}
          >
            {isCollapsed ? (
              <PanelRightOpen className={styles.panelToggleIcon} aria-hidden="true" />
            ) : (
              <PanelRightClose className={styles.panelToggleIcon} aria-hidden="true" />
            )}
          </button>
          {!isCollapsed ? <h2 className="pane-title">질문 이력</h2> : null}
          {!isCollapsed ? (
            <ClipboardClock className={styles.historyTitleIcon} aria-hidden="true" />
          ) : null}
        </div>
        {!isCollapsed ? (
          <button
            type="button"
            className={styles.newChatButton}
            onClick={handleOpenConfirm}
            aria-label="새 질문 시작"
            title="현재 대화는 확인 후 초기화됩니다."
          >
            <SquarePen className={styles.newChatIcon} aria-hidden="true" />
            <span>새 질문</span>
          </button>
        ) : null}
      </div>

      {!isCollapsed ? (
        <>
          <div className={styles.questionerFilterSection}>
            <span className={styles.questionerFilterLabel}>
              <UsersRound className={styles.questionerFilterTitleIcon} aria-hidden="true" />
              질문자 선택
            </span>
            {/* 왼쪽: 질문자 셀렉트 / 오른쪽: 검색 입력(Enter 또는 검색 버튼으로 적용) */}
            <div className={styles.questionerFilterRow}>
              <div className={styles.questionerFilterField}>
                <select
                  id="history-questioner-filter"
                  className={styles.questionerFilterSelect}
                  value={effectiveSelectedQuestioner}
                  onChange={(event) => handleSelectQuestioner(event.target.value)}
                  aria-label="질문자 필터"
                >
                  {visibleQuestionerOptions.map((option) => (
                    <option key={option.key} value={option.key}>
                      {formatQuestionerOptionLabel(option.label, option.count)}
                    </option>
                  ))}
                </select>
                <ChevronDown className={styles.questionerFilterChevron} aria-hidden="true" />
              </div>

              <div className={styles.questionerSearchField}>
                <Search className={styles.questionerSearchIcon} aria-hidden="true" />
                <input
                  type="text"
                  className={styles.questionerSearchInput}
                  value={questionerSearchKeyword}
                  // 타이핑 중에는 draft만 갱신하고, 실제 조회는 Enter/검색 버튼에서 적용한다.
                  onChange={(event) => handleChangeQuestionerSearchKeyword(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") {
                      event.preventDefault();
                      applyQuestionerSearchKeyword();
                    }
                  }}
                  placeholder="질문자 검색"
                  aria-label="질문자 검색"
                />
                {questionerSearchKeyword.trim().length > 0 ? (
                  <button
                    type="button"
                    className={styles.questionerSearchClearButton}
                    onClick={clearQuestionerSearchKeyword}
                    aria-label="검색어 초기화"
                    title="검색어 초기화"
                  >
                    X
                  </button>
                ) : null}
                <button
                  type="button"
                  className={styles.questionerSearchButton}
                  onClick={applyQuestionerSearchKeyword}
                >
                  검색
                </button>
              </div>
            </div>
          </div>

          <div className={styles.historyListWrap}>
            <div className={styles.historyList}>
              {historyItems.map((item) => (
                <HistoryCard
                  key={item.id}
                  item={item}
                  onSelect={handleSelectChat}
                  onDelete={handleDeleteChat}
                />
              ))}
              {isHistoryEmpty && (
                <p className={styles.emptyHistoryText}>선택한 질문자의 이력이 없습니다.</p>
              )}
            </div>
          </div>

          <div className={styles.paginationRow}>
            <button
              type="button"
              className={styles.pageButton}
              onClick={goFirstPage}
              disabled={currentPage <= 1}
              aria-label="첫 페이지로 이동"
              title="첫 페이지"
            >
              <ChevronFirst className={styles.pageButtonIcon} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.pageButton}
              onClick={goPrevPage}
              disabled={currentPage <= 1}
              aria-label="이전 페이지로 이동"
              title="이전 페이지"
            >
              <ChevronLeft className={styles.pageButtonIcon} aria-hidden="true" />
            </button>
            <div className={styles.pageNumbers}>
              {paginationItems.map((item, index) => {
                if (typeof item !== "number") {
                  return (
                    <span key={`${item}-${index}`} className={styles.pageEllipsis} aria-hidden="true">
                      ...
                    </span>
                  );
                }

                const isActive = item === currentPage;
                return (
                  <button
                    key={item}
                    type="button"
                    className={`${styles.pageButton} ${isActive ? styles.pageButtonActive : ""}`}
                    onClick={() => goPage(item)}
                  >
                    {item}
                  </button>
                );
              })}
            </div>
            <button
              type="button"
              className={styles.pageButton}
              onClick={goNextPage}
              disabled={currentPage >= totalPages}
              aria-label="다음 페이지로 이동"
              title="다음 페이지"
            >
              <ChevronRight className={styles.pageButtonIcon} aria-hidden="true" />
            </button>
            <button
              type="button"
              className={styles.pageButton}
              onClick={goLastPage}
              disabled={currentPage >= totalPages}
              aria-label="마지막 페이지로 이동"
              title="마지막 페이지"
            >
              <ChevronLast className={styles.pageButtonIcon} aria-hidden="true" />
            </button>
          </div>
        </>
      ) : null}

      {!isCollapsed && isConfirmOpen ? (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onClick={() => setIsConfirmOpen(false)}
        >
          <section
            className={styles.modalCard}
            role="dialog"
            aria-modal="true"
            aria-label="새 질문 확인"
            onClick={(event) => event.stopPropagation()}
          >
            <p className={styles.modalTitle}>새 질문을 시작할까요?</p>
            <p className={styles.modalText}>
              현재 채팅 메시지는 화면에서 초기화됩니다.
              <br />
              질문자와 모델, 프롬프트 설정은 유지됩니다.
            </p>
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.cancelButton}
                onClick={() => setIsConfirmOpen(false)}
              >
                취소
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                onClick={handleConfirmNewChat}
              >
                새 질문
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
