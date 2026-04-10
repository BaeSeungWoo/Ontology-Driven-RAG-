import api from "@/services/api";
import type { ChatItem } from '@/types/chatApi'

type HistoryResponse = {
  chat_id : number;
  questioner: string;
  title: string;
  first_asked_at: string;
  last_message_at: string | null;
}

export async function getHistory(): Promise<HistoryResponse[]> {
  const response = await api.post<ChatItem[]>("/api/history/getHistory", {});

  const payload = response.data;
  
  return payload.map((item) => ({
    chat_id: item.chat_id,
    questioner: item.asker,
    title: item.title,
    first_asked_at: item.first_asked_at,
    last_message_at: item.last_message_at
  }));
}