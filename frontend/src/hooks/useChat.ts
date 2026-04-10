import { useState } from "react";
import { askApi } from "@/services/askApi";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { MessageItem } from "@/types/chatApi";

/**
 * 기능: 채팅 상태/전송 훅
 * 이유: 화면 컴포넌트에서 API 스트리밍 상태 관리를 분리해 재사용성과 가독성을 높이기 위해
 * In: 질문, 모델, 모드, 질문자, 프롬프트명
 * Out: messages, sendQuestion, isLoading, error
 */
type SendQuestionParams = {
  question: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  questioner: string;
  promptName?: string | null;
};

export const useChat = () => {
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 기능: 질문 전송 + 스트리밍 응답 반영
   * 이유: 사용자 입력 즉시 타임라인에 반영하고, 답변은 토큰 단위로 갱신하기 위해
   * In: SendQuestionParams
   * Out: messages 상태 업데이트(유저 메시지 추가 + 답변 placeholder/스트리밍 갱신)
   */
  const sendQuestion = async ({
    question,
    llmModel,
    llmMode,
    questioner,
    promptName,
  }: SendQuestionParams) => {
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
      questioner: questioner,
      prompt_name: promptName ?? null,
      model: llmModel,
      llm_mode: llmMode,
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
