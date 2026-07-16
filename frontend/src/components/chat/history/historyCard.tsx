import { useState, type KeyboardEvent, type MouseEvent } from "react";
import { X } from "lucide-react";

import styles from "./history.module.css";

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
  recentAt: string;
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

  const cardClassName = `${styles.historyCard} ${item.isActive ? styles.historyCardActive : ""}`;
  const modelModePromptText = `· ${item.llmModelLabel} | ${item.llmModeLabel} | ${item.promptName}`;

  // 함수
  // 기능/목적: 카드 선택, 키보드 선택, 삭제 확인 모달 열기/닫기를 처리한다.
  // In: click/keydown event / Out: onSelect 호출 또는 modal state 변경
  const handleSelect = () => {
    onSelect(item.id);
  };

  const handleCardKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    handleSelect();
  };

  const handleDeleteClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
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
      aria-label="질문 이력 카드"
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
        <X className={styles.cardDeleteIcon} />
      </button>
      <p className={styles.cardTitle}>{item.title}</p>
      <p className={styles.cardModelMode}>{modelModePromptText}</p>
      <div className={styles.cardBottomRow}>
        <p className={styles.cardMeta}>· {item.recentAt}</p>
        <p className={styles.cardQuestioner}>{item.questioner}</p>
      </div>

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
