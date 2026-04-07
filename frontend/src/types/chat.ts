// 채팅 메시지 타입 정의
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
}