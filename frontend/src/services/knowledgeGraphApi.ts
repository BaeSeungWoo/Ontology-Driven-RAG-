import axios from "axios";
import api, { API_BASE_URL } from "@/services/api";
import { streamExplanation, type Explanation } from "@/services/explanationApi";

export type KnowledgeGraphResult = {
  question: string;
  corpora: string[];
  html: string;
};

export async function getKnowledgeGraph(messageId: number, signal: AbortSignal) {
  const response = await api.post<KnowledgeGraphResult>("/api/knowledge-graph", {
    message_id: messageId,
  }, { signal, baseURL: process.env.NEXT_PUBLIC_GRAPH_API_URL ?? API_BASE_URL });
  return response.data;
}

export function streamKnowledgeGraphAnswer(
  messageId: number, signal: AbortSignal, onUpdate: (result: Explanation) => void,
) {
  return streamExplanation("/api/knowledge-graph/answer", { message_id: messageId }, signal, onUpdate,
    process.env.NEXT_PUBLIC_GRAPH_API_URL ?? API_BASE_URL);
}

export function getKnowledgeGraphError(error: unknown) {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return "매뉴얼 검색 그래프를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
