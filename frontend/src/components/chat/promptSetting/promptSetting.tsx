"use client";

import { useEffect, useState } from "react";
import { Settings } from "lucide-react";

import { type LlmModel, type LlmMode } from "@/constants/llmOptions";
import { type PersonaType } from "@/constants/personaOptions";

import PromptListModal from "./promptListModal";
import MachineSelect from "./machineSelect";
import styles from "./promptSetting.module.css";

type PromptSettingProps = {
  questioner: string;
  onQuestionerChange: (value: string) => void;
  selectedLlmModel: LlmModel;
  onSelectLlmModel: (model: LlmModel) => void;
  selectedLlmMode: LlmMode;
  onSelectLlmMode: (model: LlmMode) => void;
  selectedPersonaType: PersonaType;
  onSelectPersonaType: (personaType: PersonaType) => void;
  onOpen?: () => void;
  onClose?: (applied?: { mode: LlmMode; persona: PersonaType }) => void;
};

export default function PromptSetting({
  questioner,
  onQuestionerChange,
  selectedLlmModel,
  onSelectLlmModel,
  selectedLlmMode,
  onSelectLlmMode,
  selectedPersonaType,
  onSelectPersonaType,
  onOpen,
  onClose,
}: PromptSettingProps) {
  // 내부 state
  // 기능/목적: 서비스 설정 모달의 열림 상태와 필수값 누락 여부를 관리한다.
  const [isOpen, setIsOpen] = useState(false);
  const [draftModel, setDraftModel] = useState(selectedLlmModel);
  const [draftMode, setDraftMode] = useState(selectedLlmMode);
  const [draftPersona, setDraftPersona] = useState(selectedPersonaType);

  const isQuestionerMissing = questioner.trim().length === 0;


  // 함수
  // 기능/목적: 서비스 설정 모달과 질문자 입력 변경을 상위 Chat 상태와 연결한다.
  // In: questioner value / Out: modal open state, parent state 변경
  const handleOpenModal = () => {
    setDraftModel(selectedLlmModel);
    setDraftMode(selectedLlmMode);
    setDraftPersona(selectedPersonaType);
    onOpen?.();
    setIsOpen(true);
  };

  const handleCloseModal = () => {
    setIsOpen(false);
    onClose?.();
  };

  const handleApplyModal = () => {
    onSelectLlmModel(draftModel);
    onSelectLlmMode(draftMode);
    onSelectPersonaType(draftPersona);
    setIsOpen(false);
    onClose?.({ mode: draftMode, persona: draftPersona });
  };

  const handleChangeQuestioner = (value: string) => {
    onQuestionerChange(value);
  };

  // 함수: 키보드 이벤트
  // 기능/목적: 모달이 열려 있을 때 ESC 키로 빠르게 닫을 수 있게 한다.
  useEffect(() => {
    if (!isOpen) return;

    const onEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
        onClose?.();
      }
    };

    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [isOpen, onClose]);

  // render
  return (
    <div className={styles.headerControls}>
      <MachineSelect />
      <div className={styles.questionerField}>
        <label htmlFor="questioner-input" className={styles.questionerLabel}>질문자</label>
        <input
          id="questioner-input"
          type="text"
          aria-required="true"
          aria-invalid={isQuestionerMissing}
          value={questioner}
          onChange={(event) => handleChangeQuestioner(event.target.value)}
          className={[styles.questionerInput, isQuestionerMissing ? styles.questionerInputMissing : ""].join(" ")}
          placeholder="질문자명 입력"
        />
        <fieldset className={styles.questionerBorder} aria-hidden="true">
          <legend>질문자</legend>
        </fieldset>
      </div>
      <button
        type="button"
        className={styles.settingsButton}
        onClick={handleOpenModal}
        aria-label="서비스 설정"
        aria-haspopup="dialog"
        aria-expanded={isOpen}
        title="서비스 설정"
      >
        <Settings size={25} aria-hidden="true" />
      </button>

      {isOpen && (
        <PromptListModal
          onClose={handleCloseModal}
          onApply={handleApplyModal}
          selectedLlmModel={draftModel}
          onSelectLlmModel={setDraftModel}
          selectedLlmMode={draftMode}
          onSelectLlmMode={setDraftMode}
          selectedPersonaType={draftPersona}
          onSelectPersonaType={setDraftPersona}
        />
      )}
    </div>
  );
}
