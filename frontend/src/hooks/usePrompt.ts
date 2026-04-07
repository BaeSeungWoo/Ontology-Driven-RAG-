import { useCallback } from "react";
import {
  createPrompt,
  getPromptList as getPromptListApi,
  updatePrompt as updatePromptApi,
} from "@/services/promptApi";
import type {
  CreatePromptPayload,
  PromptSelectableRow,
  PromptRow,
  UpdatePromptPayload,
} from "@/types/prompt";

/**
 * usePrompt
 *
 * 목적:
 * - 프롬프트 도메인에서 필요한 "조회/추가/수정" 호출을 한 곳에서 제공
 * - 모달 UI에서 바로 사용할 수 있도록 selectYN(선택 여부) 가공 로직 포함
 */
export const usePrompt = () => {
  /**
   * 프롬프트 목록 조회
   * In: 없음
   * Out: PromptSelectableRow[]
   */
  const getPromptList = useCallback(async (): Promise<PromptSelectableRow[]> => {
    return getPromptListApi();
  }, []);

  /**
   * 프롬프트 추가
   * In: prompt_name, prompt_txt, create_user
   * Out: 생성된 PromptRow
   */
  const addPrompt = useCallback(async (payload: CreatePromptPayload): Promise<PromptRow> => {
    return createPrompt(payload);
  }, []);

  /**
   * 프롬프트 수정
   * In: prompt_no + 수정할 필드
   * Out: 수정된 PromptRow
   */
  const updatePrompt = useCallback(async (payload: UpdatePromptPayload): Promise<PromptRow> => {
    return updatePromptApi(payload);
  }, []);

  return {
    getPromptList,
    addPrompt,
    updatePrompt,
  };
};
