/**
 * LLM 관련 선택 옵션 모음.
 * - LLM_MODEL_OPTIONS: 백엔드 factory_id와 1:1로 매핑되는 모델 선택 목록
 * - 추후 llm_mode 선택이 필요하면 같은 파일에 MODE 옵션을 추가해 함께 관리한다.
 */

export type LlmModel = "ollama_config" | "openai_config" | "anthropic_config" | "google_config";
export type LlmMode = "base" | "rag" | "graph";

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
];

