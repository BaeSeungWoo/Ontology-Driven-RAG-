import api from "@/services/api";
import type {
  HistoryPaginationPayload,
  HistoryPaginationResponse,
  HistoryQuestionerCount,
  HistoryQuestionerPayload,
  HistoryResponse,
  HistorySearchMode,
  HistorySearchResponse,
} from "@/types/historyApi";
import type { MessageFeedback } from "@/types/chatApi";

export async function searchHistory(mode: HistorySearchMode, feedback: MessageFeedback | "평가" | null): Promise<HistorySearchResponse[]> {
  const response = await api.post<HistorySearchResponse[]>("/api/history/search", { mode, feedback });
  return response.data;
}

export async function getHistory(): Promise<HistoryResponse[]> {
  const response = await api.post<HistoryResponse[]>("/api/history/getHistory", {});
  return response.data;
}

export async function getHistoryPagination(
  payload: HistoryPaginationPayload
): Promise<HistoryPaginationResponse> {
  const response = await api.post<HistoryPaginationResponse>("/api/history/getHistoryPagination", payload);
  return response.data;
}

export async function getHistoryQuestioner(
  payload: HistoryQuestionerPayload
): Promise<HistoryPaginationResponse> {
  const response = await api.post<HistoryPaginationResponse>("/api/history/getHistoryQuestioner", payload);
  return response.data;
}

export async function getHistoryQuestionerCounts(): Promise<HistoryQuestionerCount[]> {
  const response = await api.post<HistoryQuestionerCount[]>("/api/history/getHistoryQuestioner", {});
  return response.data;
}

export async function deleteHistorySession(sessionId: number): Promise<void> {
  await api.delete(`/api/history/sessions/${sessionId}`);
}
