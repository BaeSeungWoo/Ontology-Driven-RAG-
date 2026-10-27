export type HistoryResponse = {
  sessionId: number;
  machineCode?: string;
  machineName?: string | null;
  questioner: string;
  title: string;
  llmModel: string;
  llmMode: string;
  promptNo: number;
  promptName: string;
  personaType?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type HistorySearchMode = "sessions" | "messages";
export type HistorySearchResponse = HistoryResponse & {
  messageId?: number;
  targetMessageId?: number;
  question?: string | null;
  answerPreview?: string;
  feedback?: import("./chatApi").MessageFeedback | null;
  messageCreatedAt?: string;
};

export type HistoryPaginationPayload = {
  page: number;
  page_size: number;
};

export type HistoryQuestionerPayload = {
  questioner: string;
  page: number;
  page_size: number;
};

export type HistoryPaginationResponse = {
  rows: HistoryResponse[];
  total_count: number;
  total_pages: number;
  page: number;
  page_size: number;
};

export type HistoryQuestionerCount = {
  questioner: string;
  count: number;
};
