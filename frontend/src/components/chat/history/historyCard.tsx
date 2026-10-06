import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import { createPortal } from "react-dom";

import { PERSONA_OPTIONS } from "@/constants/personaOptions";

import styles from "./history.module.css";
import personaStyles from "../persona.module.css";

export type HistoryItem = {
  id: number;
  title: string;
  questioner: string;
  llmModel: string;
  llmMode: string;
  promptNo: number | null;
  llmModelLabel: string;
  llmModeLabel: string;
  promptName: string;
  personaType?: string | null;
  recentAt: string;
  recentAtTimestamp: number;
  isActive?: boolean;
};

type HistoryCardProps = {
  item: HistoryItem;
  onSelect: (chatId: number) => void;
  onDelete: (chatId: number) => Promise<void>;
};

export default function HistoryCard({ item, onSelect, onDelete }: HistoryCardProps) {
  // 내부 state
  // 기능/목적: 대화 삭제 확인 모달의 열림 상태를 관리한다.
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<{ left: number; top: number } | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const titleRef = useRef<HTMLParagraphElement>(null);

  useLayoutEffect(() => {
    if (!tooltipPosition || !tooltipRef.current) return;
    const { width, height } = tooltipRef.current.getBoundingClientRect();
    const left = Math.max(8, Math.min(tooltipPosition.left, window.innerWidth - width - 8));
    const top = Math.max(8, Math.min(tooltipPosition.top, window.innerHeight - height - 8));
    if (left !== tooltipPosition.left || top !== tooltipPosition.top) setTooltipPosition({ left, top });
  }, [tooltipPosition]);

  useEffect(() => {
    if (!tooltipPosition) return;
    const hide = () => setTooltipPosition(null);
    window.addEventListener("scroll", hide, true);
    window.addEventListener("resize", hide);
    return () => {
      window.removeEventListener("scroll", hide, true);
      window.removeEventListener("resize", hide);
    };
  }, [tooltipPosition]);

  const cardClassName = `${styles.historyCard} ${item.isActive ? styles.historyCardActive : ""}`;
  const personaLabel = PERSONA_OPTIONS.find(option => option.value === item.personaType)?.label ?? "페르소나 미기록";

  // 함수
  // 기능/목적: 카드 선택, 키보드 선택, 삭제 확인 모달 열기/닫기를 처리한다.
  // In: click/keydown event / Out: onSelect 호출 또는 modal state 변경
  const handleSelect = () => {
    setTooltipPosition(null);
    onSelect(item.id);
  };

  const handleCardKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target !== event.currentTarget) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    handleSelect();
  };

  const handleDeleteClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setTooltipPosition(null);
    setIsDeleteConfirmOpen(true);
  };

  const handleCloseDeleteConfirm = () => {
    setIsDeleteConfirmOpen(false);
  };

  const handleConfirmDelete = async () => {
    await onDelete(item.id);
    setIsDeleteConfirmOpen(false);
  };

  // render
  return (
    <div
      role="button"
      tabIndex={0}
      className={cardClassName}
      aria-label={item.title}
      aria-pressed={Boolean(item.isActive)}
      aria-describedby={tooltipPosition ? `history-tooltip-${item.id}` : undefined}
      onMouseEnter={event => {
        if (isDeleteConfirmOpen) return;
        const title = titleRef.current;
        if (title) {
          const overflow = Math.max(0, (title.firstElementChild as HTMLElement).offsetWidth - title.clientWidth);
          title.dataset.overflowing = String(overflow > 0);
          title.style.setProperty("--title-travel", `-${overflow}px`);
          title.style.setProperty("--title-duration", `${Math.max(1, overflow / 35)}s`);
        }
        const rect = event.currentTarget.getBoundingClientRect();
        setTooltipPosition({ left: rect.right + 10, top: rect.top });
      }}
      onMouseLeave={() => setTooltipPosition(null)}
      onClick={handleSelect}
      onKeyDown={handleCardKeyDown}
    >
      <button
        type="button"
        className={styles.cardDeleteButton}
        aria-label="대화 삭제"
        title="대화 삭제"
        onClick={handleDeleteClick}
      >
        <span aria-hidden="true">×</span>
      </button>
      <p ref={titleRef} className={styles.cardTitle}><span>{item.title}</span></p>

      {tooltipPosition && createPortal(
        <div ref={tooltipRef} id={`history-tooltip-${item.id}`} role="tooltip" className={styles.historyTooltip} style={tooltipPosition}>
          <p className={styles.tooltipTitle}>{item.title}</p>
          <div className={styles.tooltipTags}>
            <span>{item.llmModelLabel}</span><span className={personaStyles.theme} data-persona={item.personaType}>{personaLabel}</span><span>{item.llmModeLabel}</span>
          </div>
          <div className={styles.tooltipMeta}>
            <span>{item.questioner}</span><span>{item.recentAt}</span>
          </div>
        </div>, document.body
      )}

      {isDeleteConfirmOpen && (
        <div
          className={styles.modalBackdrop}
          role="presentation"
          onClick={handleCloseDeleteConfirm}
        >
          <section
            className={styles.modalCard}
            role="dialog"
            aria-modal="true"
            aria-label="대화 삭제 확인"
            onClick={(event) => event.stopPropagation()}
          >
            <p className={styles.modalTitle}>이 대화를 삭제할까요?</p>
            <p className={styles.modalText}>삭제한 대화는 복구할 수 없습니다.</p>
            <div className={styles.modalActions}>
              <button
                type="button"
                className={styles.cancelButton}
                onClick={handleCloseDeleteConfirm}
              >
                취소
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                onClick={handleConfirmDelete}
              >
                삭제
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
