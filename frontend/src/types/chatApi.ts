/**
 * 채팅 API 공통 타입 정의
 * - 서비스 계층과 훅/컴포넌트가 동일한 계약을 사용하도록 모아둔 파일
 */

/** 메시지 작성 주체 */
export type ChatRole = "user" | "assistant";

/** 채팅 목록/상세에서 사용하는 채팅 메타 정보 */
export type ChatItem = {
  chat_id: number;
  asker: string;
  title: string;
  first_asked_at: string;
  last_message_at: string | null;
};

/** 채팅 타임라인의 단일 메시지 */
export type MessageItem = {
  message_id: number;
  chat_id: number;
  role: ChatRole;
  content: string;
  prompt_no?: number | null;
  prompt_name?: string | null;
  model?: string | null;
  created_at: string;
};

/** 채팅 생성 요청 바디 */
export type CreateChatPayload = {
  asker: string;
  title: string;
};

/** 메시지 생성 요청 바디 */
export type CreateMessagePayload = {
  role: ChatRole;
  content: string;
  prompt_no?: number | null;
  prompt_name?: string | null;
  model?: string | null;
};
