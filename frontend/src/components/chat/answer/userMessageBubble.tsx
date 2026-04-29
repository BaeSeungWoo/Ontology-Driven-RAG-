import { MessageCircleQuestionMark } from "lucide-react";

import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

import { formatTimeLabel } from "./chatDate";

type UserMessageBubbleProps = {
  message: AnswerMessage;
};

export default function UserMessageBubble({ message }: UserMessageBubbleProps) {
  // =========================
  // state
  // =========================

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 사용자 질문 본문을 줄 단위 배열로 분리한다.
   * 목적: 개행이 포함된 질문을 원문 형태 그대로 렌더링한다.
   * In: message.text
   * Out: string[]
   */
  const getTextLines = () => {
    return message.text.split("\n");
  };

  /**
   * 기능: 사용자 질문 시각 라벨을 생성한다.
   * 목적: 질문 메타(시각)를 일관된 포맷으로 표시한다.
   * In: message.createdAt
   * Out: timeLabel(string)
   */
  const getTimeLabel = () => {
    return formatTimeLabel(message.createdAt);
  };

  const textLines = getTextLines();
  const timeLabel = getTimeLabel();

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return (
    <article className={`${styles.messageItem} ${styles.userMessage}`}>
      <ul className={styles.userMetaColumn} aria-label="질문 시각 정보">
        <li className={styles.userTimeLabel}>{timeLabel}</li>
      </ul>

      <div className={styles.messageBody}>
        <div className={styles.messageRoleRow}>
          <p className={styles.messageRole}>질문</p>
          <MessageCircleQuestionMark className={styles.messageRoleIcon} aria-hidden="true" />
        </div>
        <div className={styles.messageText}>
          {textLines.map((line, textLineIndex) => (
            <p key={`${message.id}-${textLineIndex}`}>{line || "\u00A0"}</p>
          ))}
        </div>
      </div>
    </article>
  );
}
