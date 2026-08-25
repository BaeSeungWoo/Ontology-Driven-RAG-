/**
 * 기능: 채팅 설정에서 사용하는 LLM 모델/모드 옵션과 타입을 정의한다.
 * 목적: 화면 선택값과 API 전송값의 계약을 한 곳에서 일관되게 관리한다.
 * In: 모델/모드 value-label 쌍 목록
 * Out: LlmModel, LlmMode, LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS
 */

export type LlmModel = "ollama_config" | "openai_config" | "anthropic_config" | "google_config";
// export type LlmMode = "base" | "rag" | "graph";
export type LlmMode = "base" | "rag" | "graph" | "chroma" | "faiss" | "kg" | "ladder" | "multimodal" | "judge";

export type LlmModelOption = {
  value: LlmModel;
  label: string;
};

export type LlmModeOption = {
  value: LlmMode;
  label: string;
};

export const LLM_MODEL_OPTIONS: LlmModelOption[] = [
  { value: "ollama_config", label: "Ollama" },
  { value: "openai_config", label: "OpenAI" },
  { value: "anthropic_config", label: "Anthropic" },
  { value: "google_config", label: "Gemini" },
];

export const LLM_MODE_OPTIONS: LlmModeOption[] = [
  { value: "base", label: "Base" },
  { value: "rag", label: "RAG" },
  { value: "graph", label: "Graph" },
  { value: "chroma", label: "Chroma" },
  { value: "faiss", label: "FAISS" },
  { value: "kg", label: "KG" },
  { value: "ladder", label: "Ladder" },
  { value: "multimodal", label: "MultiModal" },
  { value: "judge", label: "Judge" },
];
