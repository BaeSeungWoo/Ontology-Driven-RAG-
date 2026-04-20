import { Fragment, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
  isActive?: boolean;
  onActivate?: (assistantMessageId: string) => void;
};

export default function AssistantMessageBubble({
  message,
  isActive = false,
  onActivate,
}: AssistantMessageBubbleProps) {
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

  /**
   * 기능: 답변 버블 클릭/키보드 활성 이벤트를 처리한다.
   * 목적: 활성 답변 상태를 사용자가 명시적으로 선택할 수 있게 한다.
   * In: click event 또는 keydown(Enter/Space)
   * Out: onActivate(message.id) 호출
   */
  const handleActivate = () => {
    onActivate?.(message.id);
  };

  /**
   * 기능: 키보드로 답변 버블 활성화를 지원한다.
   * 목적: 마우스 외 입력에서도 활성 답변 선택이 가능하도록 접근성을 보장한다.
   * In: keyboard event
   * Out: Enter/Space 입력 시 onActivate(message.id) 호출
   */
  const handleActivateByKeyboard = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    handleActivate();
  };

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return (
    <article className={`${styles.messageItem} ${styles.assistantMessage}`}>
      <div
        className={`${styles.messageBody} ${styles.messageBodyInteractive} ${
          isActive ? styles.messageBodyActive : ""
        }`}
        onClick={handleActivate}
        onKeyDown={handleActivateByKeyboard}
        tabIndex={0}
        role="button"
        aria-pressed={isActive}
        aria-label="답변 선택"
      >
        <span
          className={`${styles.messageSelectBadge} ${
            isActive ? styles.messageSelectBadgeActive : ""
          }`}
          aria-hidden="true"
        >
          {isActive ? "선택됨" : "근거 보기"}
        </span>
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
