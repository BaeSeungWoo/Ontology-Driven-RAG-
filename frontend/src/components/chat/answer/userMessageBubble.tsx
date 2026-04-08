import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";
import { formatTimeLabel } from "./chatDate";

type UserMessageBubbleProps = {
  message: AnswerMessage;
};

export default function UserMessageBubble({ message }: UserMessageBubbleProps) {
  // 질문 메시지: 우측 버블 + 좌측 메타(모델/프롬프트/시각)
  return (
    <article className={`${styles.messageItem} ${styles.userMessage}`}>
      <div className={styles.userMetaColumn}>
        <span className={styles.userMetaLabel}>모델: {message.llmModel ?? "-"}</span>
        <span className={styles.userMetaLabel}>프롬프트: {message.promptName ?? "-"}</span>
        <span className={styles.userTimeLabel}>{formatTimeLabel(message.createdAt)}</span>
      </div>

      <div className={styles.messageBody}>
        <p className={styles.messageRole}>질문</p>
        <div className={styles.messageText}>
          {message.text.split("\n").map((line, textLineIndex) => (
            <p key={`${message.id}-${textLineIndex}`}>{line || "\u00A0"}</p>
          ))}
        </div>
      </div>
    </article>
  );
}

