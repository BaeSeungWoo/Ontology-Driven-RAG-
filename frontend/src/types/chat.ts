import type { LlmModel, LlmMode } from "@/constants/llmOptions";

/**
 * 기능: Answer 화면 전용 메시지 타입
 * 이유: API 타입과 분리해 화면 렌더에 필요한 메타를 명확히 유지하기 위해
 * In: answer.tsx에서 정규화한 메시지 데이터
 * Out: user/assistant 버블 컴포넌트의 공통 props 타입
 */
export type AnswerMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
  questioner?: string | null;
  llmModel?: LlmModel;
  llmMode?: LlmMode;
  promptName?: string | null;
};
