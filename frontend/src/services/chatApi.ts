import api, { API_BASE_URL } from "@/services/api";
import { canUseRagPreset } from "@/services/promptApi";
import type {
  CreateSessionPayload,
  CreateSessionResponse,
  MessageItem,
  MessageFeedback,
} from "@/types/chatApi";
import type { ChatMetadata } from "@/types/chatApi";

export async function updateMessageFeedback(messageId: number, feedback: MessageFeedback | null): Promise<void> {
  await api.put(`/api/history/messages/${messageId}/feedback`, { feedback }, { timeout: 15_000 });
}

export async function updateMessageReason(messageId: number, reason: string): Promise<void> {
  await api.put(`/api/history/messages/${messageId}/reason`, { reason }, { timeout: 15_000 });
}

export type AnswerSnapshot = {
  message_id: number;
  content: string;
  metadata: ChatMetadata;
  status: "running" | "completed" | "cancelled" | "failed" | "save_failed";
};

export async function startAnswer(factoryId: string, model: string, sessionId: number,
  question: string, mode: string, persona: string, restoreMemory: boolean, retryId?: number,
  selectedCitation?: { message_id: number; chunk_index: number }, promptNo?: number | null) {
  const { data } = await api.post<AnswerSnapshot & { user_message_id: number }>(`/api/chat/${model}`, {
    selected_citation: selectedCitation, background: true, session_id: String(sessionId), question, mode, persona_type: persona,
    prompt_no: canUseRagPreset(factoryId, mode, persona) ? promptNo ?? undefined : undefined,
    prompt_id: "tech_expert", restore_memory: restoreMemory, retry_message_id: retryId,
  }, { headers: { "X-Factory-Id": factoryId } });
  return data;
}

function answerPath(sessionId: number, messageId: number) {
  return `/api/history/sessions/${sessionId}/answers/${messageId}`;
}

export async function stopAnswer(factoryId: string, sessionId: number, messageId: number, generationId: string) {
  await api.post(answerPath(sessionId, messageId) + "/stop", null, {
    params: { generation_id: generationId }, headers: { "X-Factory-Id": factoryId },
  });
}

// Reconnecting only subscribes to the existing job; it never submits the question again.
export async function watchAnswer(factoryId: string, sessionId: number, messageId: number,
  apply: (answer: AnswerSnapshot) => void): Promise<AnswerSnapshot> {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await fetch(API_BASE_URL + answerPath(sessionId, messageId), {
        headers: { "X-Factory-Id": factoryId }, cache: "no-store",
      });
      if (!response.ok || !response.body) throw new Error("답변 상태를 조회하지 못했습니다.");
      if (response.headers.get("content-type")?.includes("application/json")) {
        const saved: AnswerSnapshot = await response.json();
        apply(saved);
        return saved;
      }
      const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += value;
          let end: number;
          while ((end = buffer.indexOf("\n")) >= 0) {
            const answer: AnswerSnapshot = JSON.parse(buffer.slice(0, end));
            buffer = buffer.slice(end + 1);
            apply(answer);
            if (answer.status !== "running") return answer;
          }
        }
      } finally {
        await reader.cancel().catch(() => {});
      }
      throw new Error("답변 상태 연결이 끊겼습니다.");
    } catch (error) {
      if (attempt >= 2) throw error;
      await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
    }
  }
}

export async function createSession(
  payload: CreateSessionPayload, factoryId: string
): Promise<CreateSessionResponse> {
  const response = await api.post<CreateSessionResponse>("/api/history/newSession", {
    ...payload,
    prompt_no: canUseRagPreset(factoryId, payload.llm_mode, payload.llm_persona) ? payload.prompt_no : undefined,
  }, { headers: { "X-Factory-Id": factoryId } });
  return response.data;
}

export async function getMessages(sessionId: number): Promise<MessageItem[]> {
  const response = await api.post<MessageItem[]>("/api/history/getMessages", {
    session_id: sessionId,
  });
  return response.data;
}
