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
  selectedMachineCode?: string;
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
  selectedMachineCode,
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
        const result = await getPromptList(selectedMachineCode);
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
  }, [getPromptList, selectedMachineCode]);
  

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
                    onSelectLlmMode(option.value === "operator" ? "rag" : option.value === "maintenance" ? "ladder" : option.value === "engineer" ? "electrical" : "cms");
                  }}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <p className={styles.llmGuideTitle}>사용 LLM 모드 선택</p>
          <div className={styles.llmRadioGroup}>
            {LLM_MODE_OPTIONS.map((option) => {
              const disabled = option.value === "cms" && selectedPersonaType !== "manager";
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
          {selectedPersonaType !== "manager" && (
            <p id="cms-mode-restriction" className={styles.llmGuideDesc}>
              CMS를 사용하려면 페르소나를 관리자로 선택하세요.
            </p>
          )}
          <p className={styles.llmGuideDesc}>
            페르소나 선택 시 현장 작업자는 RAG, 정비·보전은 Ladder, 기술 엔지니어는 전기도면 고장진단 QA, 관리자는 CMS로 자동 지정됩니다. 전기도면 QA는 백엔드의 vLLM을 사용하며 현재 M005 · DHF8000 및 M051 · DHF8000 #2 도면을 지원합니다.
          </p>
          {selectedLlmMode === "repairHistory" && (
            <p className={styles.llmGuideDesc}>
              매뉴얼로 원인과 조치를 설명하고, 증상·고장 질문에는 관련 수리 이력과 암묵지를 추가합니다.
              동일 장비 이력과 다른 장비의 유사 사례를 구분하며, 관련 사례가 없으면 매뉴얼 답변만 제공합니다.
              질문 예: “절삭유 모터가 동작하지 않고 과부하 알람이 떠. 원인과 조치가 뭐야?”
            </p>
          )}
          {selectedLlmMode === "paddleocr" && (
            <p className={styles.llmGuideDesc}>
              새 OCR은 LCV-6700 #1·#2의 신규 OCR 문서 5개 전체를 벡터·키워드로 검색하고, 답변에서 인용한 MD의 그림을 표시합니다.
              기존 RAG와 비교할 때 같은 모델·페르소나를 선택하고 새 질문으로 실행하세요.
            </p>
          )}
          <p className={styles.llmGuideDesc}>
            추천질문은 Ollama·vLLM 모델의 테스트 기능이며, 현장 작업자·RAG, 정비·보전·Ladder, 전기도면 고장진단 QA, 관리자·CMS 조합에서 표시·실행됩니다. 추천질문이 모드를 변경하지는 않습니다. 기술 엔지니어는 전기도면을 사용하며, 관리자·CMS는 현재 장비의 2026-10-19 작업일 집계를 사용합니다.
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
