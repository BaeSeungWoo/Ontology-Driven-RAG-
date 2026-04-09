import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
};

export default function AssistantMessageBubble({ message }: AssistantMessageBubbleProps) {
  const normalizedText = message.text.trim();
  const isLoading = normalizedText.length === 0 || normalizedText === "(응답 생성 중...)";

  // 답변 메시지: 좌측 버블 + Markdown(GFM) 렌더링
  return (
    <article className={`${styles.messageItem} ${styles.assistantMessage}`}>
      <div className={styles.messageBody}>
        <p className={styles.messageRole}>답변</p>
        {isLoading ? (
          <div className={styles.assistantLoading} aria-live="polite">
            <p className={styles.loadingText}>답변 생성중입니다.</p>
            <span className={styles.loadingDots} aria-hidden="true">
              ...
            </span>
          </div>
        ) : (
          <div className={styles.markdownContent}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
          </div>
        )}
      </div>
    </article>
  );
}

