"use client";

import { useEffect, useState } from "react";
import PromptListModal from "./promptListModal";
import type { PromptRow } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions"
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
  // ============================================================
  // 상태(State)
  // - 프롬프트 모달 표시 여부와 필수값 검증 상태를 관리한다.
  // ============================================================

  // In: "프롬프트 목록" 버튼 클릭 / 모달 닫기 이벤트
  // Out: 프롬프트 모달 열림/닫힘 상태
  const [isOpen, setIsOpen] = useState(false);

  // In: questioner 입력값
  // Out: 질문자 미입력 여부
  const isQuestionerMissing = questioner.trim().length === 0;

  // In: selectedPrompt 값
  // Out: 프롬프트 미선택 여부
  const isPromptMissing = selectedPrompt === null;

  // In: 질문자/프롬프트 검증 결과
  // Out: 필수값 미완료 여부(경고 배지/힌트 표시 조건)
  const isRequiredMissing = isQuestionerMissing || isPromptMissing;

  // ============================================================
  // 함수(Functions)
  // - 입력 이벤트와 모달 제어 이벤트를 상위 콜백에 연결한다.
  // ============================================================

  /**
   * 모달 열기
   * In: "프롬프트 목록" 버튼 클릭
   * Out: isOpen=true
   */
  const handleOpenModal = () => {
    setIsOpen(true);
  };

  /**
   * 모달 닫기
   * In: 모달 닫기 버튼/백드롭 클릭/ESC
   * Out: isOpen=false
   */
  const handleCloseModal = () => {
    setIsOpen(false);
  };

  /**
   * 질문자 입력 변경
   * In: input change event
   * Out: 상위 상태(questioner) 갱신
   */
  const handleChangeQuestioner = (value: string) => {
    onQuestionerChange(value);
  };

  /**
   * 프롬프트 적용
   * In: 모달에서 선택한 PromptRow
   * Out: 상위 selectedPrompt 갱신 + 모달 닫기
   */
  const handleApplyPrompt = (prompt: PromptRow) => {
    onSelectPrompt(prompt);
    setIsOpen(false);
  };

  /**
   * ESC 키로 모달 닫기
   * In: isOpen=true 상태에서 키보드 이벤트 발생
   * Out: Escape 입력 시 isOpen=false
   */
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

  // ============================================================
  // 최종 렌더(Render)
  // - 질문자 입력, 프롬프트 선택 버튼, 현재 선택 정보, 모달을 렌더한다.
  // ============================================================

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between gap-2">
        <h2 className="pane-title">{"프롬프트 설정"}</h2>
        {isRequiredMissing && <span className={styles.requiredBadge}>{"필수"}</span>}
      </div>

      {isRequiredMissing && (
        <div className={styles.promptHint}>{"질문자 입력과 프롬프트 선택을 완료해주세요."}</div>
      )}

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

      <p className="m-0 text-[12px] text-(--chat-muted-text)">
        {"현재 선택: "}
        {selectedPrompt ? selectedPrompt.prompt_name : "-"}
      </p>

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
