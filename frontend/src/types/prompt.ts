export type PromptRow = {
  prompt_no: number;
  prompt_name: string;
  prompt_txt: string;
  create_user: string;
};

export type LlmModel = "ollama" | "openai" | "anthropic" | "gemini";

export type PromptApiItem = PromptRow;

export type PromptListResponse = PromptApiItem[] | { data?: PromptApiItem[] };

export type PromptMutationPayload = {
  prompt_no?: number;
  prompt_txt?: string;
  prompt_name?: string;
  create_user?: string;
};

/** 프롬프트 추가 요청 바디 */
export type CreatePromptPayload = {
  prompt_name: string;
  prompt_txt: string;
  create_user: string;
};

/** 프롬프트 수정 요청 바디 */
export type UpdatePromptPayload = {
  prompt_no: number;
  prompt_name?: string;
  prompt_txt?: string;
};

/** 모달 선택 상태를 포함한 프롬프트 행 */
export type PromptSelectableRow = PromptRow & {
  SEL_YN: "Y" | "N";
};
