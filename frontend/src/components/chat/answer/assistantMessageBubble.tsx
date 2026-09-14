import { Fragment, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import styles from "./answer.module.css";
import { toCitationDisplayText } from "./citationText";
import type { AnswerMessage } from "@/types/chat";
import LadderDiagrams from "./ladderDiagram";
import AssetPanel from "../assetPanel";
import { getMessageReferenceItems, getReferenceItems } from "../citation/citationUtils";

type AssistantMessageBubbleProps = {
  message: AnswerMessage;
  isActive?: boolean;
  isGenerating?: boolean;
  selectedCitationChunkIndex?: number | null;
  onActivate?: (assistantMessageId: string) => void;
  onCitationSelect?: (assistantMessageId: string, chunkIndex: number) => void;
};

export default function AssistantMessageBubble({
  message,
  isActive = false,
  isGenerating = false,
  selectedCitationChunkIndex = null,
  onActivate,
  onCitationSelect,
}: AssistantMessageBubbleProps) {
  // =========================
  // state
  // =========================
  const normalizedText = message.text.trim();
  // 빈 답변 placeholder와 실제 스트리밍 중 상태를 분리해 spinner 유지 시간을 제어한다.
  const isPlaceholderLoading =
    normalizedText.length === 0 || normalizedText === "(응답 생성 중...)";
  const isThinking = isGenerating || isPlaceholderLoading;
  const promptName = message.metadata?.prompt_name || message.promptName || "프롬프트 미기록";
  const elapsedMs = message.metadata?.elapsed_ms;
  const elapsedLabel = typeof elapsedMs === "number" && Number.isFinite(elapsedMs) && elapsedMs >= 0
    ? `${(elapsedMs / 1000).toFixed(1)}s`
    : "시간 미기록";
  const citedChunkCount = message.metadata?.used_chunks
    ? new Set(message.metadata.used_chunks.map((chunk) => chunk.index)).size
    : getReferenceItems(message.text).length;
  const additionalLadderCount = getMessageReferenceItems({
    content: message.text,
    llm_mode: message.llmMode,
    metadata: message.metadata,
  }).filter((item) => item.additional).length;

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

  const handleCitationClick = (
    event: React.MouseEvent<HTMLAnchorElement>,
    href?: string
  ) => {
    const match = href?.match(/^#chunk-(\d+)$/);
    if (!match) return;
    event.preventDefault();
    event.stopPropagation();
    handleActivate();
    onCitationSelect?.(message.id, Number(match[1]));
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
    if (event.target !== event.currentTarget) return;
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    handleActivate();
  };

  return (
    <article className={`${styles.messageItem} ${styles.assistantMessage} ${message.llmMode === "ladder" ? styles.ladderMessage : ""}`}>
      <div className={styles.assistantMetaRow}>
        <span className={styles.assistantAiBadge}>AI</span>
        <span className={styles.assistantPromptName}>{promptName}</span>
        {isThinking ? (
          <span className={styles.assistantGenerationStatus} role="status">
            <span className={styles.assistantThinkingSpinner} aria-hidden="true" />
            생성 중
          </span>
        ) : (
          <span className={styles.assistantStats}>
            <span aria-label={`응답 시간 ${elapsedLabel}`}>{elapsedLabel}</span>
            <span aria-hidden="true"> · </span>
            <span aria-label={`인용 청크 ${citedChunkCount}개`}>{citedChunkCount} chunks</span>
            {additionalLadderCount > 0 && (
              <>
                <span aria-hidden="true"> · </span>
                <span>추가 래더 근거 {additionalLadderCount}개</span>
              </>
            )}
          </span>
        )}
        <span
          className={`${styles.messageSelectBadge} ${
            isActive ? styles.messageSelectBadgeActive : ""
          }`}
          aria-hidden="true"
        >
          {isActive ? "선택됨" : "근거 보기"}
        </span>
      </div>
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
        {isPlaceholderLoading ? (
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
                a: ({ href, children, ...props }) => {
                  const isCitation = href?.startsWith("#chunk-");
                  const citationMatch = href?.match(/^#chunk-(\d+)$/);
                  const isCitationActive =
                    isCitation &&
                    citationMatch &&
                    Number(citationMatch[1]) === selectedCitationChunkIndex;
                  return (
                    <a
                      {...props}
                      href={href}
                      aria-label={isCitation ? `참조 ${children}` : undefined}
                      className={
                        isCitation
                          ? `${styles.citationLink} ${
                              isCitationActive ? styles.citationLinkActive : ""
                            }`
                          : undefined
                      }
                      onClick={(event) => handleCitationClick(event, href)}
                    >
                      {children}
                    </a>
                  );
                },
              }}
            >
              {toCitationDisplayText(message.text)}
            </ReactMarkdown>
          </div>
        )}
        {!isThinking && (
          <AssetPanel
            inline
            activeAssistantMessage={{
              message_id: message.id,
              content: message.text,
              metadata: message.metadata,
            }}
            selectedCitation={selectedCitationChunkIndex === null ? null : {
              messageId: message.id,
              chunkIndex: selectedCitationChunkIndex,
            }}
            onCitationSelect={(messageId, chunkIndex) => {
              handleActivate();
              onCitationSelect?.(messageId, chunkIndex);
            }}
          />
        )}
      </div>
      {message.llmMode === "ladder" && !isThinking && (
        <LadderDiagrams
          chunks={message.metadata?.chunks ?? []}
          answerText={message.text}
          onSource={(index) => {
            handleActivate();
            onCitationSelect?.(message.id, index);
          }}
        />
      )}
    </article>
  );
}
