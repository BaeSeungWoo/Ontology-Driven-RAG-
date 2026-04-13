import { Fragment, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
};

export default function AssistantMessageBubble({ message }: AssistantMessageBubbleProps) {
  // =========================
  // state
  // =========================
  const normalizedText = message.text.trim();
  const isLoading = normalizedText.length === 0 || normalizedText === "(응답 생성 중...)";

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 텍스트 내부의 <br> 문자열을 실제 줄바꿈 노드로 치환한다.
   * 목적: Markdown 표 구조를 유지하면서 셀/문단 내부 줄바꿈만 처리한다.
   * In: children(ReactNode)
   * Out: ReactNode[]
   */
  const renderWithBreakTags = (children: ReactNode) => {
    const nodes = Array.isArray(children) ? children : [children];

    return nodes.flatMap((node, nodeIndex) => {
      if (typeof node !== "string") {
        return [<Fragment key={`node-${nodeIndex}`}>{node}</Fragment>];
      }

      const parts = node.split(/<br\s*\/?>/gi);

      return parts.flatMap((part, partIndex) => {
        const key = `text-${nodeIndex}-${partIndex}`;
        if (partIndex === 0) return [<Fragment key={key}>{part}</Fragment>];
        return [
          <br key={`br-${key}`} />,
          <Fragment key={key}>{part}</Fragment>,
        ];
      });
    });
  };

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
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
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                p: ({ children, ...props }) => <p {...props}>{renderWithBreakTags(children)}</p>,
                li: ({ children, ...props }) => <li {...props}>{renderWithBreakTags(children)}</li>,
                td: ({ children, ...props }) => <td {...props}>{renderWithBreakTags(children)}</td>,
                th: ({ children, ...props }) => <th {...props}>{renderWithBreakTags(children)}</th>,
              }}
            >
              {message.text}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </article>
  );
}
