import { useState } from "react";
import HistoryCard, { type HistoryItem } from "./historyCard";
import styles from "./history.module.css";
import type { ChatItem } from "@/types/chatApi";

type HistoryProps = {
  onNewChat: () => void;
  hasMessages: boolean;
  chats: ChatItem[];
  selectedChatId: number | null;
  onSelectChat: (chatId: number) => void;
};

function formatDateTime(value: string | null): string {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`;
}

export default function History({
  onNewChat,
  hasMessages,
  chats,
  selectedChatId,
  onSelectChat,
}: HistoryProps) {
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);

  const historyItems: HistoryItem[] = chats.map((chat) => ({
    id: chat.chat_id,
    title: chat.title,
    questioner: chat.asker,
    recentAt: formatDateTime(chat.last_message_at ?? chat.first_asked_at),
    isActive: selectedChatId === chat.chat_id,
  }));

  const handleOpenConfirm = () => {
    if (!hasMessages) return;
    setIsConfirmOpen(true);
  };

  const handleConfirmNewChat = () => {
    onNewChat();
    setIsConfirmOpen(false);
  };

  return (
    <div className={styles.historyRoot}>
      <div className={styles.headerRow}>
        <h2 className="pane-title">질문 이력</h2>
        <button
          type="button"
          className={styles.newChatButton}
          onClick={handleOpenConfirm}
          disabled={!hasMessages}
          aria-label="새 질문 시작"
          title={
            hasMessages
              ? "현재 대화를 비우고 새 질문을 시작합니다."
              : "아직 초기화할 대화가 없습니다."
          }
        >
          + 새 질문
        </button>
      </div>

      <div className={styles.historyListWrap}>
        <div className={styles.historyList}>
          {historyItems.map((item) => (
            <HistoryCard key={item.id} item={item} onSelect={onSelectChat} />
          ))}
        </div>
      </div>

      <div className={styles.paginationRow}>
        <button type="button" className={styles.pageButton}>
          이전
        </button>
        <div className={styles.pageNumbers}>
          <button type="button" className={`${styles.pageButton} ${styles.pageButtonActive}`}>
            1
          </button>
        </div>
        <button type="button" className={styles.pageButton}>
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
