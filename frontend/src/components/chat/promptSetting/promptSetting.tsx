"use client";

import { useEffect, useState } from "react";
import { Settings, TriangleAlert } from "lucide-react";

import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import type { PromptRow } from "@/types/prompt";

import PromptListModal from "./promptListModal";
import styles from "./promptSetting.module.css";

type PromptSettingProps = {
  questioner: string;
  onQuestionerChange: (value: string) => void;
  selectedPrompt: PromptRow | null;
  selectedLlmModel: LlmModel;
  onSelectLlmModel: (model: LlmModel) => void;
  selectedLlmMode: LlmMode;
  onSelectLlmMode: (model: LlmMode) => void;
  selectedPersonaType: PersonaType;
  onSelectPersonaType: (personaType: PersonaType) => void;
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
  selectedPersonaType,
  onSelectPersonaType,
  onSelectPrompt,
}: PromptSettingProps) {
  // 내부 state
  // 기능/목적: 프롬프트 목록 모달의 열림 상태와 필수값 누락 여부를 관리한다.
  const [isOpen, setIsOpen] = useState(false);

  const isQuestionerMissing = questioner.trim().length === 0;
  const isPromptMissing = selectedPrompt === null;
  const isRequiredMissing = isQuestionerMissing || isPromptMissing;

  // 함수
  // 기능/목적: 프롬프트 목록 모달과 질문자 입력 변경을 상위 Chat 상태와 연결한다.
  // In: questioner value, PromptRow / Out: modal open state, parent state 변경
  const handleOpenModal = () => {
    setIsOpen(true);
  };

  const handleCloseModal = () => {
    setIsOpen(false);
  };

  const handleChangeQuestioner = (value: string) => {
    onQuestionerChange(value);
  };

  const handleApplyPrompt = (prompt: PromptRow) => {
    onSelectPrompt(prompt);
    setIsOpen(false);
  };

  // 함수: 키보드 이벤트
  // 기능/목적: 모달이 열려 있을 때 ESC 키로 빠르게 닫을 수 있게 한다.
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

  // render
  return (
    <div className="flex flex-col gap-2.5">
      <div className={styles.promptHeader}>
        <div className={styles.promptTitleGroup}>
          <h2 className={`pane-title ${styles.promptTitle}`}>프롬프트 설정</h2>
          <Settings className={styles.promptTitleIcon} aria-hidden="true" />
        </div>
        <div
          className={`${styles.headerRightGroup} ${
            !isRequiredMissing ? styles.headerRightGroupHidden : ""
          }`}
          aria-hidden={!isRequiredMissing}
        >
          <span className={styles.requiredNotice}>
            <span className={styles.requiredBadge}>필수</span>
            <TriangleAlert className={styles.requiredNoticeIcon} aria-hidden="true" />
            <span className={styles.requiredMessage}>
              [질문자, 프롬프트] 입력을 완료해주세요.
            </span>
          </span>
        </div>
      </div>

      <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-2">
        <label
          htmlFor="questioner-input"
          className="text-[13px] font-semibold text-(--chat-title-color)"
        >
          질문자
        </label>
        <input
          id="questioner-input"
          type="text"
          value={questioner}
          onChange={(event) => handleChangeQuestioner(event.target.value)}
          className={`${styles.questionerInput} ${
            isQuestionerMissing ? styles.questionerInputMissing : ""
          }`}
          placeholder="질문자를 입력하세요."
        />
      </div>

      <button
        type="button"
        className="w-full cursor-pointer rounded-[10px] border-0 bg-[color-mix(in_srgb,var(--chat-title-color)_78%,#111_22%)] px-3.5 py-3 text-[20px] leading-[1.2] font-bold text-(--chat-pane-bg) hover:bg-[color-mix(in_srgb,var(--chat-title-color)_64%,var(--chat-pane-bg)_36%)]"
        onClick={handleOpenModal}
      >
        프롬프트 목록
      </button>

      {isOpen && (
        <PromptListModal
          onClose={handleCloseModal}
          selectedPrompt={selectedPrompt}
          selectedLlmModel={selectedLlmModel}
          onSelectLlmModel={onSelectLlmModel}
          selectedLlmMode={selectedLlmMode}
          onSelectLlmMode={onSelectLlmMode}
          selectedPersonaType={selectedPersonaType}
          onSelectPersonaType={onSelectPersonaType}
          onApplyPrompt={handleApplyPrompt}
        />
      )}
    </div>
  );
}
