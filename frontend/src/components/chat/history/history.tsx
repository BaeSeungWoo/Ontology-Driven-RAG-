import { useState } from "react";
import HistoryCard from "./historyCard";
import type { HistoryItem } from "./historyCard";
import styles from "./history.module.css";
import { useHistoryPanel } from "@/hooks/useHistoryPanel";

/**
 * 기능: History 컴포넌트 입력 props 타입을 정의한다.
 * 목적: 상위 컴포넌트와의 데이터/이벤트 계약을 명확히 한다.
 * In: 선택 세션 id, 세션 선택 콜백, 새 질문 콜백, 리프레시 키
 * Out: HistoryProps 타입 정보
 */
type HistoryProps = {
  selectedSessionId: number | null;
  // 세션 선택 시 해당 이력의 설정값을 함께 전달해 우측 설정과 동기화한다.
  onSelectSession: (sessionId: number, sessionMeta?: HistorySessionMeta) => void;
  onStartNewChat?: () => void;
  refreshKey?: number;
};

/**
 * 기능: 히스토리 선택 시 상위로 전달할 세션 메타 타입.
 * 목적: 질문자뿐 아니라 모델/모드/프롬프트까지 함께 동기화할 수 있게 한다.
 * In: HistoryItem 일부 필드
 * Out: HistorySessionMeta 타입 정보
 */
type HistorySessionMeta = Pick<
  HistoryItem,
  "questioner" | "llmModel" | "llmMode" | "promptNo" | "promptName"
>;

/**
 * 기능: 질문 이력 패널(필터 + 페이지네이션 + 카드 목록)을 렌더링한다.
 * 목적: 데이터 동기화 로직(훅)과 UI 렌더를 분리해 가독성과 유지보수성을 높인다.
 * In: HistoryProps
 * Out: JSX Element
 */
export default function History({
  selectedSessionId,
  onSelectSession,
  onStartNewChat,
  refreshKey = 0,
}: HistoryProps) {
  // 페이지 버튼 렌더 토큰: 숫자 페이지와 좌/우 말줄임 토큰을 함께 사용한다.
  type PaginationItem = number | "ellipsis-left" | "ellipsis-right";

  // =========================
  // State
  // =========================
  /**
   * 기능: 새 질문 확인 모달 표시 여부를 관리한다.
   * 목적: 실수 클릭으로 대화가 초기화되는 것을 방지한다.
   * In: 새 질문 버튼 클릭/모달 버튼 클릭
   * Out: isConfirmOpen(boolean)
   */
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 히스토리 데이터/필터/페이지네이션 동기화를 담당하는 훅.
   * 목적: UI와 API/상태 관리 로직을 분리해 history.tsx를 렌더 중심으로 유지한다.
   * In: selectedSessionId, refreshKey
   * Out: 카드 목록, 필터 상태, 페이지네이션 핸들러, 스크롤 제어 값
   */
  const {
    canScrollQuestionerLeft,
    canScrollQuestionerRight,
    currentPage,
    effectiveSelectedQuestioner,
    goNextPage,
    goPage,
    goPrevPage,
    handleQuestionerFilterScroll,
    handleSelectQuestioner,
    historyItems,
    isHistoryEmpty,
    questionerFilterScrollRef,
    totalPages,
    updateQuestionerScrollButtonState,
    visibleQuestionerOptions,
    resetQuestionerFilter,
  } = useHistoryPanel({
    selectedSessionId,
    refreshKey,
  });

  /**
   * 기능: 새 질문 확인 모달을 연다.
   * 목적: 대화 초기화 전 사용자 확인을 받는다.
   * In: 새 질문 버튼 클릭
   * Out: isConfirmOpen=true
   */
  const handleOpenConfirm = () => {
    setIsConfirmOpen(true);
  };

  /**
   * 기능: 새 질문 확인을 확정한다.
   * 목적: 상위 컴포넌트에 새 세션 시작 이벤트를 전달한다.
   * In: 모달의 "새 질문" 클릭
   * Out: isConfirmOpen=false, 질문자 필터 전체 초기화, onStartNewChat 호출
   */
  const handleConfirmNewChat = () => {
    setIsConfirmOpen(false);
    resetQuestionerFilter();
    onStartNewChat?.();
  };

  /**
   * 기능: 카드 클릭 시 해당 세션을 선택한다.
   * 목적: 상위에서 선택 세션 메시지를 로드하고 질문자/모델/모드/프롬프트를 동기화한다.
   * In: sessionId
   * Out: onSelectSession(sessionId, sessionMeta)
   */
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

  /**
   * 기능: 현재 페이지 기준으로 축약 페이지네이션 목록을 생성한다.
   * 목적: 페이지 수가 많아도 번호 버튼이 한 줄에서 안정적으로 보이게 한다.
   * In: currentPage, totalPages
   * Out: PaginationItem[](숫자 페이지 + 말줄임 토큰)
   */
  const getPaginationItems = (): PaginationItem[] => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }

    if (currentPage <= 4) {
      return [1, 2, 3, 4, 5, "ellipsis-right", totalPages];
    }

    if (currentPage >= totalPages - 3) {
      return [1, "ellipsis-left", totalPages - 4, totalPages - 3, totalPages - 2, totalPages - 1, totalPages];
    }

    return [1, "ellipsis-left", currentPage - 1, currentPage, currentPage + 1, "ellipsis-right", totalPages];
  };

  const paginationItems = getPaginationItems();

  // =========================
  // Render
  // =========================
  return (
    <div className={styles.historyRoot}>
      <div className={styles.headerRow}>
        <h2 className="pane-title">질문 이력</h2>
        <button
          type="button"
          className={styles.newChatButton}
          onClick={handleOpenConfirm}
          aria-label="새 질문 시작"
          title="현재는 렌더링 확인용 버튼입니다."
        >
          + 새 질문
        </button>
      </div>

      <div className={styles.questionerFilterSection}>
        {/* <p className={styles.questionerFilterTitle}>질문자 필터</p> */}
        <div className={styles.questionerFilterRow}>
          <button
            type="button"
            className={styles.questionerFilterArrow}
            onClick={() => handleQuestionerFilterScroll("left")}
            aria-label="질문자 필터 왼쪽으로 이동"
            disabled={!canScrollQuestionerLeft}
          >
            <span className={styles.questionerFilterArrowIcon}>{"<"}</span>
          </button>

          <div
            className={styles.questionerFilterScroll}
            ref={questionerFilterScrollRef}
            onScroll={updateQuestionerScrollButtonState}
          >
            {visibleQuestionerOptions.map((option) => {
              const isActive = effectiveSelectedQuestioner === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  className={`${styles.questionerFilterChip} ${
                    isActive ? styles.questionerFilterChipActive : ""
                  }`}
                  onClick={() => handleSelectQuestioner(option.key)}
                  aria-pressed={isActive}
                >
                  <span>{option.label}</span>
                  <span className={styles.questionerFilterCount}>{option.count}</span>
                </button>
              );
            })}
          </div>

          <button
            type="button"
            className={styles.questionerFilterArrow}
            onClick={() => handleQuestionerFilterScroll("right")}
            aria-label="질문자 필터 오른쪽으로 이동"
            disabled={!canScrollQuestionerRight}
          >
            <span className={styles.questionerFilterArrowIcon}>{">"}</span>
          </button>
        </div>
      </div>

      <div className={styles.historyListWrap}>
        <div className={styles.historyList}>
          {historyItems.map((item) => (
            <HistoryCard key={item.id} item={item} onSelect={handleSelectChat} />
          ))}
          {isHistoryEmpty && <p className={styles.emptyHistoryText}>선택한 질문자의 이력이 없습니다.</p>}
        </div>
      </div>

      <div className={styles.paginationRow}>
        <button
          type="button"
          className={styles.pageButton}
          onClick={goPrevPage}
          disabled={currentPage <= 1}
        >
          이전
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
        >
          다음
        </button>
      </div>

      {isConfirmOpen && (
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
              질문자, 모델, 프롬프트 설정은 유지됩니다.
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
      )}
    </div>
  );
}
