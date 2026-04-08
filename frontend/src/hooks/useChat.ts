import { useState } from "react";
import { askApi } from "@/services/AskApi";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { MessageItem } from "@/types/chatApi";

/**
 * 질문/답변 상태를 관리하는 훅.
 * - 질문 전송 시 user 메시지와 assistant placeholder를 먼저 추가한다.
 * - askApi 스트리밍 청크를 받아 assistant 메시지 content를 실시간으로 갱신한다.
 */
type SendQuestionParams = {
  question: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
};

export const useChat = () => {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sendQuestion = async ({ question, llmModel, llmMode }: SendQuestionParams) => {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;

    setIsLoading(true);
    setError(null);

    const now = new Date().toISOString();
    const userMessageId = Date.now();
    const assistantMessageId = userMessageId + 1;

    const userMessage: MessageItem = {
      message_id: userMessageId,
      chat_id: 0,
      role: "user",
      content: normalizedQuestion,
      created_at: now,
    };

    const assistantPlaceholder: MessageItem = {
      message_id: assistantMessageId,
      chat_id: 0,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);

    try {
      let streamedAnswer = "";

      const result = await askApi({
        question: normalizedQuestion,
        llmModel,
        llmMode,
        onChunk: (chunk) => {
          streamedAnswer += chunk;
          setMessages((prev) =>
            prev.map((item) =>
              item.message_id === assistantMessageId
                ? { ...item, content: streamedAnswer || "(응답 생성 중...)" }
                : item
            )
          );
        },
      });

      setMessages((prev) =>
        prev.map((item) =>
          item.message_id === assistantMessageId
            ? { ...item, content: result.answer || streamedAnswer || "(응답 없음)" }
            : item
        )
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : "질문 요청 중 오류가 발생했습니다.";
      setError(message);

      setMessages((prev) =>
        prev.map((item) =>
          item.message_id === assistantMessageId
            ? { ...item, content: `요청 실패: ${message}` }
            : item
        )
      );
    } finally {
      setIsLoading(false);
    }
  };

  return {
    messages,
    sendQuestion,
    isLoading,
    error,
  };
};
