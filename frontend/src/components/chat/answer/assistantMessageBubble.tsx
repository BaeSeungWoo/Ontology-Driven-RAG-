import { Fragment, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
};

/**
 * 기능: 텍스트 안의 `<br>` 문자열을 실제 줄바꿈 엘리먼트(`<br />`)로 변환
 * 이유: Markdown 테이블 구조는 유지하면서 셀 내부 `<br>`만 줄바꿈 처리하기 위해
 * In: ReactMarkdown이 넘겨주는 children(문자열/노드 혼합 가능)
 * Out: `<br />`가 삽입된 ReactNode 배열
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

export default function AssistantMessageBubble({ message }: AssistantMessageBubbleProps) {
  const normalizedText = message.text.trim();
  const isLoading = normalizedText.length === 0 || normalizedText === "(응답 생성 중...)";

  /**
   * 기능: 답변 버블 렌더링
   * 이유: 응답 대기 상태와 실제 Markdown 렌더 상태를 분리해 UX를 명확히 하기 위해
   * In: AnswerMessage
   * Out: 로딩 안내 UI 또는 Markdown 렌더 UI
   */
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
                // 기능: 문단/리스트/테이블 셀 단위로만 <br> 문자열을 실제 줄바꿈으로 치환
                // 이유: 원본 markdown 전체를 치환하면 테이블 문법이 깨질 수 있기 때문
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
