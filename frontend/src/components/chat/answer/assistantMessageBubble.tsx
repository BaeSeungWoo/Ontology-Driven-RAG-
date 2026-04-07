import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
};

export default function AssistantMessageBubble({ message }: AssistantMessageBubbleProps) {
  // 답변 메시지: 좌측 버블 + Markdown(GFM) 렌더링
  return (
    <article className={`${styles.messageItem} ${styles.assistantMessage}`}>
      <div className={styles.messageBody}>
        <p className={styles.messageRole}>답변</p>
        <div className={styles.markdownContent}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
        </div>
      </div>
    </article>
  );
}

