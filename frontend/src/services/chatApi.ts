import api from "@/services/api";
import type { LlmModel } from "@/types/prompt";
import type {
  ChatItem,
  MessageItem,
  CreateChatPayload,
  CreateMessagePayload,
} from "@/types/chatApi";

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

/**
 * 채팅 목록 조회
 * - GET /api/chats
 * - asker가 있으면 질문자 기준 필터링
 */
export async function getChats(asker?: string): Promise<ChatItem[]> {
  const response = await api.get<ChatItem[]>("/api/chats", {
    params: asker ? { asker } : undefined,
  });
  return response.data;
}

/**
 * 단일 채팅 메타 정보 조회
 * - GET /api/chats/:chatId
 */
export async function getChat(chatId: number): Promise<ChatItem> {
  const response = await api.get<ChatItem>(`/api/chats/${chatId}`);
  return response.data;
}

/**
 * 새 채팅 생성
 * - POST /api/chats
 * - 메시지를 붙이기 전 채팅 컨테이너를 먼저 생성
 */
export async function createChat(payload: CreateChatPayload): Promise<ChatItem> {
  const response = await api.post<ChatItem>("/api/chats", payload);
  return response.data;
}

/**
 * 채팅 삭제
 * - DELETE /api/chats/:chatId
 * - 서버에서 연관 메시지도 함께 정리한다는 정책 가정
 */
export async function deleteChat(chatId: number): Promise<void> {
  await api.delete(`/api/chats/${chatId}`);
}

/**
 * 메시지 목록 조회
 * - GET /api/chats/:chatId/messages
 */
export async function getMessages(chatId: number): Promise<MessageItem[]> {
  const response = await api.get<MessageItem[]>(`/api/chats/${chatId}/messages`);
  return response.data;
}

/**
 * 메시지 1건 추가
 * - POST /api/chats/:chatId/messages
 * - role(user/assistant)과 content를 저장
 */
export async function createMessage(
  chatId: number,
  payload: CreateMessagePayload,
): Promise<MessageItem> {
  const response = await api.post<MessageItem>(`/api/chats/${chatId}/messages`, payload);
  return response.data;
}
