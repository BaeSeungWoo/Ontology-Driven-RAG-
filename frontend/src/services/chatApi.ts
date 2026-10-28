import api, { API_BASE_URL, factoryHeaders } from "@/services/api";
import type {
  AskRequest,
  AskResponse,
  CreateMessagePayload,
  CreateMessageResponse,
  CreateSessionPayload,
  CreateSessionResponse,
  MessageItem,
  MessageFeedback,
  UpdateMessagePayload,
  UpdateMessageResponse,
} from "@/types/chatApi";
import type { ChatMetadata } from "@/types/chatApi";

export async function updateMessageFeedback(messageId: number, feedback: MessageFeedback): Promise<void> {
  await api.put(`/api/history/messages/${messageId}/feedback`, { feedback }, { timeout: 15_000 });
}

export async function updateMessageReason(messageId: number, reason: string): Promise<void> {
  await api.put(`/api/history/messages/${messageId}/reason`, { reason }, { timeout: 15_000 });
}

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

class RetryableChatError extends Error {}

export async function askApi(request: AskRequest): Promise<AskResponse> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await askOnce({ ...request, restoreMemory: request.restoreMemory || attempt > 0 });
    } catch (error) {
      if (request.llmMode === "electrical" || attempt >= 2 || !(error instanceof TypeError || error instanceof RetryableChatError)) {
        throw error;
      }
      request.onRetry?.(attempt + 1);
      await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
    }
  }
}

async function askOnce({
  sessionId,
  question,
  llmModel,
  llmMode,
  personaType,
  restoreMemory = false,
  onChunk,
  onProgress,
}: AskRequest): Promise<AskResponse> {
  const controller = new AbortController();
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  const waitForData = async <T,>(operation: Promise<T>): Promise<T> => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      return await Promise.race([
        operation,
        new Promise<never>((_, reject) => {
          timer = setTimeout(() => {
            reject(new RetryableChatError(llmMode === "electrical" ? "전기도면 QA 응답 제한시간을 초과했습니다." : "2분 동안 서버 응답이 없어 연결을 중단했습니다."));
            controller.abort();
          }, llmMode === "electrical" ? 1_860_000 : 120_000);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  };

  try {
    const response = await waitForData(fetch(`${API_BASE_URL}/api/chat/${llmModel}`, {
      signal: controller.signal,
      method: "POST",
      headers: {
        ...factoryHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: String(sessionId),
        question,
        mode: llmMode,
        prompt_id: "tech_expert",
        persona_type: personaType,
        restore_memory: restoreMemory,
      }),
    }));

    if (!response.ok) {
      if (llmMode === "electrical") {
        const detail = await response.json().catch(() => null);
        throw new Error(typeof detail?.detail === "string" ? detail.detail : `전기도면 QA 요청 실패: ${response.status}`);
      }
      if ([408, 429, 500, 502, 503, 504].includes(response.status)) {
        throw new RetryableChatError(`서버 연결 실패: ${response.status}`);
      }
      throw new Error(`질문 요청 실패: ${response.status}`);
    }

    if (!response.body) {
      throw new RetryableChatError("스트리밍 응답 본문이 없습니다.");
    }

    reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let answerText = "";
    let metadataRaw = "";
    let metadataMode = true;
    let pending = "";

    while (true) {
      const { done, value } = await waitForData(reader.read());
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });

      // 진행·오류 프레임을 먼저 처리하고, METADATA 이후의 내용만 답변으로 전달한다.
      if (metadataMode) {
        pending += chunk;
        let splitIndex: number;
        while ((splitIndex = pending.indexOf("\n\n")) >= 0) {
          const frame = pending.slice(0, splitIndex);
          pending = pending.slice(splitIndex + 2);
          if (frame.startsWith("PROGRESS:")) {
            const message: unknown = JSON.parse(frame.slice("PROGRESS:".length));
            if (typeof message === "string") onProgress?.(message);
            else if (message && typeof message === "object" && "message" in message && typeof message.message === "string") {
              onProgress?.(message.message, "detail" in message && typeof message.detail === "string" ? message.detail : undefined);
            }
            continue;
          }
          if (frame.startsWith("ERROR:")) {
            const message: unknown = JSON.parse(frame.slice("ERROR:".length));
            throw new Error(typeof message === "string" ? message : "전기도면 QA 처리에 실패했습니다.");
          }
          metadataRaw = frame;
          metadataMode = false;
          if (pending) {
            answerText += pending;
            onChunk?.(pending);
          }
          pending = "";
          break;
        }
        continue;
      }

      answerText += chunk;
      onChunk?.(chunk);
    }

    const tail = decoder.decode();
    if (tail && !metadataMode) {
      answerText += tail;
      onChunk?.(tail);
    }
    if (metadataMode || !answerText.trim()) {
      throw new RetryableChatError("답변을 받기 전에 서버 연결이 종료되었습니다.");
    }

    return {
      answer: answerText.trim(),
      metadata: parseMetadata(metadataRaw),
    };
  } finally {
    controller.abort();
    void reader?.cancel().catch(() => {});
  }
}

export async function createSession(
  payload: CreateSessionPayload
): Promise<CreateSessionResponse> {
  const response = await api.post<CreateSessionResponse>("/api/history/newSession", {
    ...payload,
  });
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
  const response = await api.put<UpdateMessageResponse>(`/api/history/messages/${messageId}`, payload, { timeout: 15_000 });
  return response.data;
}
