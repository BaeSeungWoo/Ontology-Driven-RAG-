import { useEffect, useMemo, useRef } from "react";
import styles from "./answer.module.css";
import type { MessageItem } from "@/types/chatApi";
import type { AnswerMessage } from "@/types/chat";
import type { LlmModel } from "@/constants/llmOptions";
import { getDateKey } from "./chatDate";
import ChatDateDivider from "./chatDateDivider";
import UserMessageBubble from "./userMessageBubble";
import AssistantMessageBubble from "./assistantMessageBubble";

/**
 * 기능: 답변 영역 타임라인 렌더링(날짜 구분 + 질문/답변 말풍선)
 * 이유: 메시지 메타를 UI 친화적으로 정규화하고, 날짜 변경 시 시각적으로 구분하기 위해
 * In: API MessageItem[]
 * Out: 화면 렌더용 AnswerMessage[] + 날짜 구분선/버블 컴포넌트 트리
 */
type AnswerProps = {
  messages: MessageItem[];
};

// 기능: 백엔드 model(string)을 프론트 LlmModel 유니온으로 안전하게 축소
const LLM_MODELS: LlmModel[] = [
  "ollama_config",
  "openai_config",
  "anthropic_config",
  "google_config",
];

const toLlmModel = (value?: string | null): LlmModel | undefined => {
  if (!value) return undefined;
  return LLM_MODELS.includes(value as LlmModel) ? (value as LlmModel) : undefined;
};

export default function Answer({ messages }: AnswerProps) {
  const scrollRef = useRef<HTMLElement | null>(null);
  const shouldAutoScrollRef = useRef(true);

  /**
   * 기능: 메시지 정규화
   * 이유: 렌더 계층에서 타입/필드명 차이를 신경 쓰지 않게 하기 위해
   * In: MessageItem
   * Out: AnswerMessage
   */
  const normalizedMessages: AnswerMessage[] = messages.map((message) => {
    const createdAt = Date.parse(message.created_at);

    return {
      id: String(message.message_id),
      role: message.role,
      text: message.content ?? "",
      createdAt: Number.isNaN(createdAt) ? message.message_id : createdAt,
      questioner: message.questioner ?? null,
      llmModel: toLlmModel(message.model),
      llmMode: message.llm_mode ?? undefined,
      promptName: message.prompt_name ?? null,
    };
  });

  const scrollAnchor = useMemo(
    () =>
      normalizedMessages
        .map((message) => `${message.id}:${message.text.length}:${message.createdAt}`)
        .join("|"),
    [normalizedMessages]
  );

  /**
   * 기능: 스트리밍 응답 자동 하단 스크롤
   * 이유: 새 토큰이 추가될 때 최신 답변을 바로 보이게 하기 위해
   * In: scrollAnchor(메시지 길이/생성시각 변화)
   * Out: answerScroll의 scrollTop 갱신
   */
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !shouldAutoScrollRef.current) return;
    container.scrollTop = container.scrollHeight;
  }, [scrollAnchor]);

  const handleAnswerScroll = () => {
    const container = scrollRef.current;
    if (!container) return;

    // 사용자가 아래쪽에 있을 때만 자동 스크롤 유지
    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= 48;
  };

  return (
    <div className={styles.answerRoot}>
      <h2 className="pane-title">답변</h2>

      <section
        ref={scrollRef}
        className={styles.answerScroll}
        aria-label="답변 내용"
        onScroll={handleAnswerScroll}
      >
        {normalizedMessages.length === 0 && (
          <p className="pane-placeholder">질문을 보내면 답변이 여기에 표시됩니다.</p>
        )}

        {normalizedMessages.length > 0 && (
          <div className={styles.messageList}>
            {normalizedMessages.map((message, messageIndex) => {
              const previousMessage = normalizedMessages[messageIndex - 1];

              /**
               * 기능: 날짜 경계 계산
               * 이유: 날짜가 바뀌는 지점에만 헤더를 표시하기 위해
               * In: 현재/이전 메시지 createdAt
               * Out: isDateChanged(boolean)
               */
              const isDateChanged =
                messageIndex === 0 ||
                getDateKey(message.createdAt) !== getDateKey(previousMessage.createdAt);

              return (
                <div key={message.id}>
                  {isDateChanged && <ChatDateDivider createdAt={message.createdAt} />}
                  {message.role === "user" ? (
                    <UserMessageBubble message={message} />
                  ) : (
                    <AssistantMessageBubble message={message} />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
