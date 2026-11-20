import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import type { LadderDiagram } from "@/types/ladder";

export type ChatRole = "user" | "assistant";

export type ChatChunk = {
  index: number;
  retrieval_rank?: number;
  document: string;
  metadata: Record<string, unknown> & { ladder_diagram?: LadderDiagram };
  distance: number | null;
  similarity?: number | null;
  bm25_score?: number | null;
  rrf_score?: number | null;
  vector_rank?: number | null;
  bm25_rank?: number | null;
};

export type ChatMetadata = Record<string, unknown> & {
  ui_action?: { type: "open_document"; document: ResolvedDocument };
  progress_history?: { message: string; detail?: string; at: number }[];
  progress_started_at?: number;
  progress_updated_at?: number;
  progress_finished_at?: number;
  progress_message?: string;
  elapsed_ms?: number;
  prompt_name?: string;
  images?: string[];
  tables?: string[];
  chunks?: ChatChunk[];
  used_chunks?: ChatChunk[];
};

export type ResolvedDocument = {
  document_name: string;
  asset_url: string;
  page: number | null;
};

export type CreateSessionPayload = {
  machine_code?: string;
  questioner: string;
  title: string;
  llm_model: string;
  llm_mode: string;
  llm_persona: PersonaType;
};

export type CreateSessionResponse = {
  result: string;
  session_id: number;
};

export type MessageFeedback = "도움됨" | "틀림" | "부분도움";

export type MessageItem = {
  machine_code?: string;
  message_id: number;
  session_id: number;
  role: ChatRole;
  content: string;
  created_at: string;
  questioner?: string | null;
  model?: string | null;
  llm_mode?: string | null;
  prompt_name?: string | null;
  metadata?: ChatMetadata;
  feedback?: MessageFeedback | null;
  reason?: string | null;
};
