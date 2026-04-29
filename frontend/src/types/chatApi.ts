import type { LlmModel, LlmMode } from "@/constants/llmOptions";

export type ChatRole = "user" | "assistant";

export type AskRequest = {
  sessionId: number;
  question: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  onChunk?: (chunk: string) => void;
};

export type ChatChunk = {
  index: number;
  retrieval_rank?: number;
  document: string;
  metadata: Record<string, unknown>;
  distance: number | null;
  similarity?: number | null;
};

export type ChatMetadata = Record<string, unknown> & {
  images?: string[];
  tables?: string[];
  chunks?: ChatChunk[];
  used_chunks?: ChatChunk[];
};

export type AskResponse = {
  answer: string;
  metadata?: ChatMetadata;
};

export type CreateSessionPayload = {
  questioner: string;
  title: string;
  llm_model: string;
  llm_mode: string;
  prompt_no: number;
};

export type CreateSessionResponse = {
  result: string;
  session_id: number;
};

export type CreateMessagePayload = {
  session_id: number;
  role: ChatRole;
  content: string;
};

export type CreateMessageResponse = {
  result: string;
  message_id: number;
};

export type UpdateMessagePayload = {
  content: string;
  metadata?: ChatMetadata;
};

export type UpdateMessageResponse = {
  result: string;
};

export type MessageItem = {
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
};
