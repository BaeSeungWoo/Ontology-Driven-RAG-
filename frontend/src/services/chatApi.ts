import api, { API_BASE_URL } from "@/services/api";
import type {
  AskRequest,
  AskResponse,
  CreateMessagePayload,
  CreateMessageResponse,
  CreateSessionPayload,
  CreateSessionResponse,
  MessageItem,
  UpdateMessagePayload,
  UpdateMessageResponse,
} from "@/types/chatApi";

export async function askApi({
  sessionId,
  question,
  llmModel,
  llmMode,
  onChunk,
}: AskRequest): Promise<AskResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/${llmModel}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      session_id: String(sessionId),
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

export async function createSession(
  payload: CreateSessionPayload
): Promise<CreateSessionResponse> {
  const response = await api.post<CreateSessionResponse>("/api/history/newSession", payload);
  return response.data;
}

export async function getMessages(sessionId: number): Promise<MessageItem[]> {
  const response = await api.post<MessageItem[]>("/api/history/getMessages", {
    session_id: sessionId,
  });
  return response.data;
}

export async function createMessage(
  payload: CreateMessagePayload
): Promise<CreateMessageResponse> {
  const response = await api.post<CreateMessageResponse>("/api/history/messages", payload);
  return response.data;
}

export async function updateMessage(
  messageId: number,
  payload: UpdateMessagePayload
): Promise<UpdateMessageResponse> {
  const response = await api.put<UpdateMessageResponse>(`/api/history/messages/${messageId}`, payload);
  return response.data;
}
