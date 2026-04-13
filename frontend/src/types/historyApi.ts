export type HistoryResponse = {
  sessionId: number;
  questioner: string;
  title: string;
  llmModel: string;
  llmMode: string;
  promptNo: number;
  promptName: string;
  createdAt: string;
  updatedAt: string;
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
