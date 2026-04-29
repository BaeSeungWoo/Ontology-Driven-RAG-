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
import type { ChatMetadata } from "@/types/chatApi";

/**
 * 기능: 스트리밍 응답 선두의 METADATA 프레임을 JSON으로 파싱한다.
 * 목적: 답변 토큰과 별도로 전달된 chunk/이미지/표 정보를 화면 상태와 DB 저장에 활용한다.
 * In: metadataRaw(string)
 * Out: ChatMetadata | undefined
 */
function parseMetadata(metadataRaw: string): ChatMetadata | undefined {
  const prefix = "METADATA:";
  const normalized = metadataRaw.trim();
  if (!normalized.startsWith(prefix)) return undefined;

  try {
    const parsed = JSON.parse(normalized.slice(prefix.length));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? parsed
      : undefined;
  } catch {
    return undefined;
  }
}

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

    // 기능: 첫 번째 빈 줄 전까지는 metadata 프레임으로 처리하고 이후부터 답변 토큰으로 흘려보낸다.
    // 목적: 사용자에게는 답변만 스트리밍하면서 내부적으로 metadata를 보존한다.
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
    metadata: parseMetadata(metadataRaw),
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
