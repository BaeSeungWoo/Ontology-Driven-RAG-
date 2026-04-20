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

export const usePrompt = () => {
  // =========================
  // state
  // =========================

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 프롬프트 목록을 조회한다.
   * 목적: 프롬프트 선택 UI에서 최신 목록을 표시한다.
   * In: 없음
   * Out: PromptSelectableRow[]
   */
  const getPromptList = useCallback(async (): Promise<PromptSelectableRow[]> => {
    return getPromptListApi();
  }, []);

  /**
   * 기능: 새 프롬프트를 생성한다.
   * 목적: 사용자가 입력한 프롬프트를 서버에 저장한다.
   * In: CreatePromptPayload
   * Out: PromptRow
   */
  const addPrompt = useCallback(async (payload: CreatePromptPayload): Promise<PromptRow> => {
    return createPrompt(payload);
  }, []);

  /**
   * 기능: 기존 프롬프트를 수정한다.
   * 목적: 선택된 프롬프트의 변경 내용을 서버에 반영한다.
   * In: UpdatePromptPayload
   * Out: PromptRow
   */
  const updatePrompt = useCallback(async (payload: UpdatePromptPayload): Promise<PromptRow> => {
    return updatePromptApi(payload);
  }, []);

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return {
    getPromptList,
    addPrompt,
    updatePrompt,
  };
};
