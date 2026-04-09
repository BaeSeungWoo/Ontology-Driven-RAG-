import api from "@/services/api";
import type { LlmModel } from "@/constants/llmOptions";

/**
 * 채팅 API 서비스 레이어
 * - 채팅 이력 관련 HTTP 호출을 한 곳에서 관리
 * - React 상태 없이 요청/응답 처리만 담당
 */

export type AskQuestionPayload = {
  question: string;
  llmModel: LlmModel;
};

export type AskQuestionResponse = {
  answer?: string;
  [key: string]: unknown;
};

/**
 * 테스트용 질문 호출
 * - POST /api/askQuestion
 * - question, llmModel만 전송
 */
export async function askQuestion(payload: AskQuestionPayload): Promise<AskQuestionResponse> {
  const response = await api.post<AskQuestionResponse>("/api/askQuestion", payload);
  return response.data;
}