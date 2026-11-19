import axios from "axios";
import api, { API_BASE_URL } from "@/services/api";
import { streamExplanation, type Explanation } from "@/services/explanationApi";
import type { ManualSource } from "./explanationApi";

export type GraphNode = {
  id: string; kind: "query" | "entity" | "passage" | "table"; label: string; content: string;
  document?: string; pages?: string; caption?: string; rows?: ManualSource["rows"];
  dense?: boolean; ppr?: boolean; fact?: boolean; final?: boolean;
  dense_rank?: number; ppr_rank?: number; cosine?: number; ppr_score?: number;
};

export type GraphEdge = {
  id: string; source: string; target: string; kind: string; label?: string; cosine?: number;
  sources?: { document: string; pages: string }[];
};

export type GraphDataset = {
  id: string; title: string; nodes: GraphNode[]; edges: GraphEdge[];
  views: Record<string, { nodes: string[]; edges: string[] }>;
  index_counts: { entities: number; passages: number; tables: number };
};

export type KnowledgeGraphResult = {
  question: string;
  corpora: string[];
  datasets: GraphDataset[];
  snapshot?: string;
};

export async function getKnowledgeGraph(messageId: number, signal: AbortSignal) {
  const response = await api.post<KnowledgeGraphResult>("/api/knowledge-graph", {
    message_id: messageId,
  }, { signal, baseURL: process.env.NEXT_PUBLIC_GRAPH_API_URL ?? API_BASE_URL });
  return response.data;
}

export function streamKnowledgeGraphAnswer(
  messageId: number, signal: AbortSignal, onUpdate: (result: Explanation) => void, snapshot?: string,
) {
  return streamExplanation("/api/knowledge-graph/answer", { message_id: messageId, snapshot }, signal, onUpdate,
    process.env.NEXT_PUBLIC_GRAPH_API_URL ?? API_BASE_URL);
}

export function getKnowledgeGraphError(error: unknown) {
  if (axios.isAxiosError<{ detail?: unknown }>(error)) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return "매뉴얼 검색 그래프를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.";
}
