import { API_BASE_URL } from "@/services/api";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";

/**
 * 백엔드 /chat/{factory_id} 호출 전용 API 파일.
 * - question, llmModel(factory_id)을 POST로 전송한다.
 * - 스트리밍 응답을 읽으며 onChunk 콜백으로 토큰을 프론트 상태에 전달한다.
 */
export type AskRequest = {
  question: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  onChunk?: (chunk: string) => void;
};

export type AskResponse = {
  answer: string;
  metadataRaw?: string;
};

export async function askApi({ question, llmModel, llmMode, onChunk }: AskRequest): Promise<AskResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/${llmModel}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: "front-test-session",
      question,
      mode: llmMode,
      prompt_id: "tech_expert",
    }),
  });

  if (!response.ok) {
    throw new Error(`질문 요청 실패: ${response.status}`);
  }

  if (!response.body) {
    throw new Error("스트리밍 응답 본문이 없습니다.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let answerText = "";
  let metadataRaw = "";
  let metadataMode = true;
  let pending = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const chunk = decoder.decode(value, { stream: true });

    if (metadataMode) {
      pending += chunk;
      const splitIndex = pending.indexOf("\n\n");

      if (splitIndex >= 0) {
        metadataRaw += pending.slice(0, splitIndex + 2);
        const rest = pending.slice(splitIndex + 2);
        pending = "";
        metadataMode = false;

        if (rest) {
          answerText += rest;
          onChunk?.(rest);
        }
      }
      continue;
    }

    answerText += chunk;
    onChunk?.(chunk);
  }

  return {
    answer: answerText.trim(),
    metadataRaw,
  };
}
