import styles from "./answer.module.css";
import type { MessageItem } from "@/types/chatApi";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

/**
 * 답변 출력 UI 파일.
 * - useChat에서 받은 messages를 순서대로 렌더한다.
 * - role이 user면 "질문", assistant면 "답변" 라벨로 구분하고 Markdown으로 표시한다.
 */
type AnswerProps = {
  messages: MessageItem[];
};

export default function Answer({ messages }: AnswerProps) {
  return (
    <div className={styles.answerRoot}>
      <h2 className="pane-title">답변</h2>

      <section className={styles.answerScroll} aria-label="답변 내용">
        {messages.length === 0 && (
          <p className="pane-placeholder">질문을 보내면 답변이 여기에 표시됩니다.</p>
        )}

        {messages.length > 0 && (
          <div className={styles.messageList}>
            {messages.map((message) => (
              <div key={message.message_id}>
                <p className="pane-title">{message.role === "user" ? "질문" : "답변"}</p>
                <div className="pane-placeholder">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {message.content ?? ""}
                  </ReactMarkdown>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
