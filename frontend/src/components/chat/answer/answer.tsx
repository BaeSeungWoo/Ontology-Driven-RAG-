import { useEffect, useRef } from "react";
import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";
import type { MessageItem } from "@/types/chatApi";
import { getDateKey } from "./chatDate";
import ChatDateDivider from "./chatDateDivider";
import UserMessageBubble from "./userMessageBubble";
import AssistantMessageBubble from "./assistantMessageBubble";

type AnswerProps = {
  messages: MessageItem[];
};

export default function Answer({ messages }: AnswerProps) {
  const listEndRef = useRef<HTMLDivElement | null>(null);

  /**
   * API 응답 스키마(MessageItem)를 기존 말풍선 렌더 스키마(AnswerMessage)로 변환
   * - 기존 버블 컴포넌트 재사용을 위해 어댑터 형태로 맞춘다.
   */
  const normalizedMessages: AnswerMessage[] = messages.map((message) => ({
    id: String(message.message_id),
    role: message.role,
    text: message.content,
    createdAt: new Date(message.created_at).getTime(),
  }));

  useEffect(() => {
    // 새 메시지가 추가될 때마다 최신 답변이 보이도록 하단으로 자동 이동
    listEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [normalizedMessages]);

  return (
    <div className={styles.answerRoot}>
      <h2 className="pane-title">답변</h2>

      <section className={styles.answerScroll} aria-label="답변 내용">
        {normalizedMessages.length === 0 && (
          <p className="pane-placeholder">질문을 보내면 답변이 여기에 표시됩니다.</p>
        )}

        {normalizedMessages.length > 0 && (
          <div className={styles.messageList}>
            {normalizedMessages.map((message, index) => {
              const prev = index > 0 ? normalizedMessages[index - 1] : null;
              const currentDateKey = getDateKey(message.createdAt);
              const prevDateKey = prev ? getDateKey(prev.createdAt) : "";

              // 첫 메시지이거나 이전 메시지와 날짜가 바뀌면 날짜 구분선 노출
              const shouldShowDateDivider = currentDateKey !== prevDateKey;

              return (
                <div key={message.id}>
                  {shouldShowDateDivider && <ChatDateDivider createdAt={message.createdAt} />}

                  {message.role === "user" ? (
                    <UserMessageBubble message={message} />
                  ) : (
                    <AssistantMessageBubble message={message} />
                  )}
                </div>
              );
            })}
            <div ref={listEndRef} />
          </div>
        )}
      </section>
    </div>
  );
}

