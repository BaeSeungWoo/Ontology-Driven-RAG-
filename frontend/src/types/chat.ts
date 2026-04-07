import type { LlmModel } from "@/types/prompt";

// 채팅 타임라인 한 줄(질문/답변) 단위 데이터 모델
// - createdAt: 날짜 구분/시각 표시에 사용
// - llmModel, promptName: 질문 메시지 메타 정보(모델/프롬프트) 보존용
export type AnswerMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  createdAt: number;
  llmModel?: LlmModel;
  promptName?: string | null;
};
