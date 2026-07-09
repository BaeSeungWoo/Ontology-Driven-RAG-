import api from "@/services/api";
import type {
  CreatePromptPayload,
  MachineInfo,
  PromptListResult,
  PromptSelectableRow,
  PromptRow,
  UpdatePromptPayload,
} from "@/types/prompt";

type PromptListLegacyItem = {
  PROMPT_NO: number;
  PROMPT_NAME: string;
  PROMPT_TXT: string;
  CREATE_USER: string;
  SEL_YN: "Y" | "N";
};

type PromptListLegacyResponse =
  | PromptListLegacyItem[]
  | {
      rows: PromptListLegacyItem[];
      machine_code: string | null;
      machine_info: MachineInfo | null;
      is_main_server: boolean;
    };

const toPromptSelectableRows = (
  payload: readonly PromptListLegacyItem[],
): PromptSelectableRow[] =>
  payload.map((item) => ({
    prompt_no: item.PROMPT_NO,
    prompt_name: item.PROMPT_NAME,
    prompt_txt: item.PROMPT_TXT,
    create_user: item.CREATE_USER,
    SEL_YN: item.SEL_YN ?? "N",
  }));

/**
 * 프롬프트 기본 목록 조회(레거시를 표준으로 사용)
 * - POST /api/prompts/getPromptList
 * - 백엔드의 대문자 키 스키마를 프론트 표준 스키마로 변환
 */
export async function getPromptList(): Promise<PromptListResult> {
  const response = await api.post<PromptListLegacyResponse>("/api/prompts/getPromptList", {});
  const payload = response.data;

  if (Array.isArray(payload)) {
    return {
      rows: toPromptSelectableRows(payload),
      machineCode: null,
      machineInfo: null,
      isMainServer: false,
    };
  }

  return {
    rows: toPromptSelectableRows(payload.rows),
    machineCode: payload.machine_code,
    machineInfo: payload.machine_info,
    isMainServer: payload.is_main_server,
  };
}

/**
 * 프롬프트 추가
 * - POST /api/prompts
 */
export async function createPrompt(payload: CreatePromptPayload): Promise<PromptRow> {
  const response = await api.post<PromptRow>("/api/prompts", payload);
  return response.data;
}

/**
 * 프롬프트 수정
 * - PUT /api/prompts/:promptNo
 */
export async function updatePrompt(payload: UpdatePromptPayload): Promise<PromptRow> {
  const response = await api.put<PromptRow>(`/api/prompts/${payload.prompt_no}`, payload);
  return response.data;
}
