"use client";

import { useEffect, useState } from "react";
import PromptListModal from "./promptListModal";
import type { PromptRow } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import styles from "./promptSetting.module.css";

type PromptSettingProps = {
  questioner: string;
  onQuestionerChange: (value: string) => void;
  selectedPrompt: PromptRow | null;
  selectedLlmModel: LlmModel;
  onSelectLlmModel: (model: LlmModel) => void;
  selectedLlmMode: LlmMode;
  onSelectLlmMode: (model: LlmMode) => void;
  onSelectPrompt: (prompt: PromptRow) => void;
};

export default function PromptSetting({
  questioner,
  onQuestionerChange,
  selectedPrompt,
  selectedLlmModel,
  onSelectLlmModel,
  selectedLlmMode,
  onSelectLlmMode,
  onSelectPrompt,
}: PromptSettingProps) {
  // =========================
  // state
  // =========================
  const [isOpen, setIsOpen] = useState(false);

  const isQuestionerMissing = questioner.trim().length === 0;
  const isPromptMissing = selectedPrompt === null;
  const isRequiredMissing = isQuestionerMissing || isPromptMissing;

  // =========================
  // 함수
  // =========================
  // 모달 제어
  /**
   * 기능: 프롬프트 목록 모달을 연다.
   * 목적: 사용자가 프롬프트를 조회/선택할 수 있는 모달을 표시한다.
   * In: 프롬프트 목록 버튼 클릭
   * Out: isOpen=true
   */
  const handleOpenModal = () => {
    setIsOpen(true);
  };

  /**
   * 기능: 프롬프트 목록 모달을 닫는다.
   * 목적: 모달 닫기 액션(버튼/백드롭/외부 이벤트)에 공통으로 대응한다.
   * In: 모달 닫기 이벤트
   * Out: isOpen=false
   */
  const handleCloseModal = () => {
    setIsOpen(false);
  };

  // 입력/선택 처리
  /**
   * 기능: 질문자 입력값을 상위 상태로 전달한다.
   * 목적: 질문자 입력 상태를 부모 컴포넌트 단일 소스로 유지한다.
   * In: input value(string)
   * Out: onQuestionerChange(value) 호출
   */
  const handleChangeQuestioner = (value: string) => {
    onQuestionerChange(value);
  };

  /**
   * 기능: 모달에서 선택한 프롬프트를 적용한다.
   * 목적: 프롬프트 선택 결과를 상위 상태에 반영하고 모달을 닫는다.
   * In: prompt(PromptRow)
   * Out: onSelectPrompt(prompt) 호출 + isOpen=false
   */
  const handleApplyPrompt = (prompt: PromptRow) => {
    onSelectPrompt(prompt);
    setIsOpen(false);
  };

  // =========================
  // useEffect
  // =========================
  useEffect(() => {
    if (!isOpen) return;

    const onEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [isOpen]);

  // =========================
  // render(return)
  // =========================
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="pane-title">{"프롬프트 설정"}</h2>
        <div
          className={`${styles.headerRightGroup} ${
            !isRequiredMissing ? styles.headerRightGroupHidden : ""
          }`}
          aria-hidden={!isRequiredMissing}
        >
          <span className={styles.requiredBadge}>{"필수"}</span>
          <span className={styles.headerInlineHint}>{"질문자 입력과 프롬프트 선택을 완료해주세요."}</span>
        </div>
      </div>

      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-2">
        <label
          htmlFor="questioner-input"
          className="text-[13px] font-semibold text-(--chat-title-color)"
        >
          {"질문자"}
        </label>
        <input
          id="questioner-input"
          type="text"
          value={questioner}
          onChange={(event) => handleChangeQuestioner(event.target.value)}
          className={`${styles.questionerInput} ${
            isQuestionerMissing ? styles.questionerInputMissing : ""
          }`}
          placeholder={"질문자를 입력하세요."}
        />
      </div>

      <button
        type="button"
        className="w-full cursor-pointer rounded-[10px] border-0 bg-[color-mix(in_srgb,var(--chat-title-color)_78%,#111_22%)] px-3.5 py-3 text-[20px] leading-[1.2] font-bold text-(--chat-pane-bg) hover:bg-[color-mix(in_srgb,var(--chat-title-color)_64%,var(--chat-pane-bg)_36%)]"
        onClick={handleOpenModal}
      >
        {"프롬프트 목록"}
      </button>

      {isOpen && (
        <PromptListModal
          onClose={handleCloseModal}
          selectedPrompt={selectedPrompt}
          selectedLlmModel={selectedLlmModel}
          onSelectLlmModel={onSelectLlmModel}
          selectedLlmMode={selectedLlmMode}
          onSelectLlmMode={onSelectLlmMode}
          onApplyPrompt={handleApplyPrompt}
        />
      )}
    </div>
  );
}
