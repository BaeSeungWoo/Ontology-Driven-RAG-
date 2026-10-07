"use client";

import { useState, useEffect } from "react";
import { usePrompt } from "@/hooks/usePrompt";
import type { MachineInfo } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import { LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS } from "@/constants/llmOptions";
import { PERSONA_OPTIONS, type PersonaType } from "@/constants/personaOptions";
import MachineInfoPanel from "./machineInfoPanel";
import styles from "./promptSetting.module.css";

type PromptListModalProps = {
  onClose: () => void;
  onApply: () => void;
  selectedLlmModel: LlmModel;
  onSelectLlmModel: (model: LlmModel) => void;
  selectedLlmMode: LlmMode;
  onSelectLlmMode: (model: LlmMode) => void;
  selectedPersonaType: PersonaType;
  onSelectPersonaType: (personaType: PersonaType) => void;
};

export default function PromptListModal({
  onClose,
  onApply,
  selectedLlmModel,
  onSelectLlmModel,
  selectedLlmMode,
  onSelectLlmMode,
  selectedPersonaType,
  onSelectPersonaType,
}: PromptListModalProps) {
  const { getPromptList } = usePrompt();

  const [machineCode, setMachineCode] = useState<string | null>(null);
  const [machineInfo, setMachineInfo] = useState<MachineInfo | null>(null);
  const [isMainServer, setIsMainServer] = useState(false);

  useEffect(() => {
    let mounted = true;

    const fetchPromptList = async () => {
      try {
        const result = await getPromptList();
        if (!mounted) return;
        setMachineCode(result.machineCode);
        setMachineInfo(result.machineInfo);
        setIsMainServer(result.isMainServer);
      } catch (error) {
        console.error("프롬프트 목록 조회 실패", error);
        if (!mounted) return;
        setMachineCode(null);
        setMachineInfo(null);
        setIsMainServer(false);
      }
    };

    void fetchPromptList();

    return () => {
      mounted = false;
    };
  }, [getPromptList]);
  

  return (
    <div className={styles.modalBackdrop} onClick={onClose} role="presentation">
      <section
        className={styles.modal}
        onClick={(event) => event.stopPropagation()}
        aria-modal="true"
        role="dialog"
      >
        <header className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>서비스 설정</h3>
        </header>

        <section className={styles.llmGuideBox}>
          <p className={styles.llmGuideTitle}>사용 LLM 모델 선택</p>
          <div className={styles.llmRadioGroup}>
            {LLM_MODEL_OPTIONS.map((option) => (
              <label key={option.value} className={styles.llmRadioItem}>
                <input
                  type="radio"
                  name="llmModel"
                  value={option.value}
                  checked={selectedLlmModel === option.value}
                  onChange={() => onSelectLlmModel(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <p className={styles.llmGuideTitle}>사용 페르소나 선택</p>
          <div className={styles.llmRadioGroup}>
            {PERSONA_OPTIONS.map((option) => (
              <label key={option.value} className={styles.llmRadioItem}>
                <input
                  type="radio"
                  name="personaType"
                  value={option.value}
                  checked={selectedPersonaType === option.value}
                  onChange={() => {
                    onSelectPersonaType(option.value);
                    onSelectLlmMode(option.value === "operator" ? "rag" : option.value === "maintenance" ? "ladder" : "cms");
                  }}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <p className={styles.llmGuideTitle}>사용 LLM 모드 선택</p>
          <div className={styles.llmRadioGroup}>
            {LLM_MODE_OPTIONS.map((option) => {
              const disabled = option.value === "cms" && !["engineer", "manager"].includes(selectedPersonaType);
              return (
                <label key={option.value} className={`${styles.llmRadioItem} ${disabled ? styles.llmRadioItemDisabled : ""}`}>
                  <input
                    type="radio"
                    name="llmMode"
                    value={option.value}
                    disabled={disabled}
                    aria-describedby={disabled ? "cms-mode-restriction" : undefined}
                    checked={selectedLlmMode === option.value}
                    onChange={() => onSelectLlmMode(option.value)}
                  />
                  <span>{option.label}{disabled && " (선택 불가)"}</span>
                </label>
              );
            })}
          </div>
          {!["engineer", "manager"].includes(selectedPersonaType) && (
            <p id="cms-mode-restriction" className={styles.llmGuideDesc}>
              CMS를 사용하려면 페르소나를 기술 엔지니어 또는 관리자로 선택하세요.
            </p>
          )}
          <p className={styles.llmGuideDesc}>
            페르소나 선택 시 현장 작업자는 RAG, 정비·보전은 Ladder, 기술 엔지니어·관리자는 CMS로 자동 지정됩니다. 이후 모드를 직접 변경할 수 있습니다.
          </p>
          {selectedLlmMode === "repairHistory" && (
            <p className={styles.llmGuideDesc}>
              매뉴얼로 원인과 조치를 설명하고, 증상·고장 질문에는 관련 수리 이력과 암묵지를 추가합니다.
              동일 장비 이력과 다른 장비의 유사 사례를 구분하며, 관련 사례가 없으면 매뉴얼 답변만 제공합니다.
              질문 예: “절삭유 모터가 동작하지 않고 과부하 알람이 떠. 원인과 조치가 뭐야?”
            </p>
          )}
          <p className={styles.llmGuideDesc}>
            추천질문은 Ollama 모델의 테스트 기능이며, 현장 작업자·RAG, 정비·보전·Ladder, 기술 엔지니어 또는 관리자·CMS 조합에서만 표시·실행됩니다. 추천질문이 모드를 변경하지는 않습니다. CMS는 현재 장비의 테스트 데이터를 조회합니다. 기술 엔지니어는 2026-08-04~08-11 작업일의 알람 이력과 매뉴얼, 관리자는 2026-08-11 작업일 집계를 사용합니다.
          </p>
        </section>

        <MachineInfoPanel
          machineCode={machineCode}
          machineInfo={machineInfo}
          isMainServer={isMainServer}
        />

        <footer className={styles.modalActions}>
          <button type="button" className={`${styles.closeButton} ${styles.applyButton}`} onClick={onApply}>
            설정
          </button>
          <button type="button" className={styles.closeButton} onClick={onClose}>
            닫기
          </button>
        </footer>
      </section>
    </div>
  );
}
