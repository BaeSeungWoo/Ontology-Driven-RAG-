import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./answer.module.css";
import type { MessageItem } from "@/types/chatApi";
import type { AnswerMessage } from "@/types/chat";
import {
  LLM_MODEL_OPTIONS,
  LLM_MODE_OPTIONS,
  type LlmModel,
  type LlmMode,
} from "@/constants/llmOptions";
import { getDateKey } from "./chatDate";
import ChatDateDivider from "./chatDateDivider";
import UserMessageBubble from "./userMessageBubble";
import AssistantMessageBubble from "./assistantMessageBubble";

type AnswerProps = {
  messages: MessageItem[];
};

const LLM_MODEL_SET = new Set<LlmModel>(LLM_MODEL_OPTIONS.map((option) => option.value));
const LLM_MODE_SET = new Set<LlmMode>(LLM_MODE_OPTIONS.map((option) => option.value));

export default function Answer({ messages }: AnswerProps) {
  // =========================
  // state
  // =========================
  const scrollRef = useRef<HTMLElement | null>(null);
  const shouldAutoScrollRef = useRef(true);
  const [selectedAssistantMessage, setSelectedAssistantMessage] = useState<{
    id: string;
    assistantCountAtSelection: number;
  } | null>(null);

  // =========================
  // 함수
  // =========================
  // 메시지 정규화
  /**
   * 기능: 모델 문자열을 LlmModel 유니온으로 안전 변환한다.
   * 목적: 허용되지 않은 모델 문자열이 UI 타입으로 전파되지 않게 한다.
   * In: value(string | null | undefined)
   * Out: LlmModel | undefined
   */
  const toLlmModel = (value?: string | null): LlmModel | undefined => {
    if (!value) return undefined;
    return LLM_MODEL_SET.has(value as LlmModel) ? (value as LlmModel) : undefined;
  };

  /**
   * 기능: 모드 문자열을 LlmMode 유니온으로 안전 변환한다.
   * 목적: 허용되지 않은 모드 문자열이 UI 타입으로 전파되지 않게 한다.
   * In: value(string | null | undefined)
   * Out: LlmMode | undefined
   */
  const toLlmMode = (value?: string | null): LlmMode | undefined => {
    if (!value) return undefined;
    return LLM_MODE_SET.has(value as LlmMode) ? (value as LlmMode) : undefined;
  };

  /**
   * 기능: API 메시지 목록을 화면 렌더용 메시지 구조로 정규화한다.
   * 목적: 하위 버블 컴포넌트가 동일한 필드 계약으로 동작하도록 맞춘다.
   * In: messages(MessageItem[])
   * Out: normalizedMessages(AnswerMessage[])
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
      llmMode: toLlmMode(message.llm_mode),
      promptName: message.prompt_name ?? null,
    };
  });

  /**
   * 기능: 답변 메시지 목록을 계산한다.
   * 목적: 활성 답변 기본값(마지막 답변) 계산에 사용한다.
   * In: normalizedMessages
   * Out: assistantMessages(AnswerMessage[])
   */
  const assistantMessages = useMemo(
    () => normalizedMessages.filter((message) => message.role === "assistant"),
    [normalizedMessages]
  );

  /**
   * 기능: 화면에 적용할 활성 답변 id를 계산한다.
   * 목적: effect에서 setState 없이 클릭 선택값 또는 마지막 답변을 안정적으로 결정한다.
   * In: selectedAssistantMessageId, assistantMessages
   * Out: activeAssistantMessageId(string | null)
   */
  const activeAssistantMessageId = useMemo(() => {
    if (assistantMessages.length === 0) return null;

    const latestAssistantId = assistantMessages[assistantMessages.length - 1].id;
    if (!selectedAssistantMessage) {
      return latestAssistantId;
    }

    // 선택 이후 답변이 1개라도 추가되면 최신 답변을 자동 활성화한다.
    if (assistantMessages.length > selectedAssistantMessage.assistantCountAtSelection) {
      return latestAssistantId;
    }

    const hasSelectedAssistant = assistantMessages.some(
      (message) => message.id === selectedAssistantMessage.id
    );

    if (hasSelectedAssistant) {
      return selectedAssistantMessage.id;
    }

    return latestAssistantId;
  }, [assistantMessages, selectedAssistantMessage]);

  // 자동 스크롤
  /**
   * 기능: 메시지 변경 감지용 키를 생성한다.
   * 목적: 메시지 추가/스트리밍 갱신 시 자동 스크롤 이펙트를 안정적으로 트리거한다.
   * In: normalizedMessages
   * Out: scrollAnchor(string)
   */
  const scrollAnchor = useMemo(
    () =>
      normalizedMessages
        .map((message) => `${message.id}:${message.text.length}:${message.createdAt}`)
        .join("|"),
    [normalizedMessages]
  );

  /**
   * 기능: 스크롤 위치를 기준으로 자동 스크롤 유지 여부를 갱신한다.
   * 목적: 사용자가 위로 읽는 중에는 자동 하단 이동을 중단한다.
   * In: answerScroll onScroll 이벤트
   * Out: shouldAutoScrollRef.current(boolean)
   */
  const handleAnswerScroll = () => {
    const container = scrollRef.current;
    if (!container) return;

    const distanceFromBottom =
      container.scrollHeight - container.scrollTop - container.clientHeight;
    shouldAutoScrollRef.current = distanceFromBottom <= 48;
  };

  /**
   * 기능: 메시지 행에서 날짜 변경 여부를 판별한다.
   * 목적: 날짜가 바뀌는 지점에만 구분선을 표시한다.
   * In: currentMessage, previousMessage, messageIndex
   * Out: boolean
   */
  const isDateDividerNeeded = (
    currentMessage: AnswerMessage,
    previousMessage: AnswerMessage | undefined,
    messageIndex: number
  ) => {
    if (messageIndex === 0) return true;
    if (!previousMessage) return true;
    return getDateKey(currentMessage.createdAt) !== getDateKey(previousMessage.createdAt);
  };

  /**
   * 기능: 특정 답변 메시지를 활성 상태로 변경한다.
   * 목적: 근거/이미지 패널 연동의 기준 답변을 명시적으로 선택한다.
   * In: assistantMessageId(string)
   * Out: activeAssistantMessageId 갱신
   */
  const handleActivateAssistantMessage = (assistantMessageId: string) => {
    setSelectedAssistantMessage({
      id: assistantMessageId,
      assistantCountAtSelection: assistantMessages.length,
    });
  };

  // =========================
  // useEffect
  // =========================
  useEffect(() => {
    const container = scrollRef.current;
    if (!container || !shouldAutoScrollRef.current) return;
    container.scrollTop = container.scrollHeight;
  }, [scrollAnchor]);

  // =========================
  // render(return)
  // =========================
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
              const showDateDivider = isDateDividerNeeded(message, previousMessage, messageIndex);

              return (
                <div key={message.id}>
                  {showDateDivider && <ChatDateDivider createdAt={message.createdAt} />}
                  {message.role === "user" ? (
                    <UserMessageBubble message={message} />
                  ) : (
                    <AssistantMessageBubble
                      message={message}
                      isActive={message.id === activeAssistantMessageId}
                      onActivate={handleActivateAssistantMessage}
                    />
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
