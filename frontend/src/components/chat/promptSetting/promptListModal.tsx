"use client";

import { useMemo, useState, useEffect } from "react";
import { usePrompt } from "@/hooks/usePrompt";
import type { PromptRow, PromptSelectableRow } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import { LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS } from "@/constants/llmOptions";
import { PERSONA_OPTIONS, type PersonaType } from "@/constants/personaOptions";
import styles from "./promptSetting.module.css";

type PromptListModalProps = {
  onClose: () => void;
  selectedPrompt: PromptRow | null;
  selectedLlmModel: LlmModel;
  onSelectLlmModel: (model: LlmModel) => void;
  selectedLlmMode: LlmMode;
  onSelectLlmMode: (model: LlmMode) => void;
  selectedPersonaType: PersonaType;
  onSelectPersonaType: (personaType: PersonaType) => void;
  onApplyPrompt: (prompt: PromptRow) => void;
};

export default function PromptListModal({
  onClose,
  selectedPrompt,
  selectedLlmModel,
  onSelectLlmModel,
  selectedLlmMode,
  onSelectLlmMode,
  selectedPersonaType,
  onSelectPersonaType,
  onApplyPrompt,
}: PromptListModalProps) {
  const { getPromptList } = usePrompt();

  // 모달 내부 선택 상태(적용 버튼 누르기 전까지 임시 유지)
  const [selectedPromptNo, setSelectedPromptNo] = useState<number | null>(
    selectedPrompt?.prompt_no ?? null,
  );

  // 레거시 엔드포인트에서 받은 전체 프롬프트 목록
  const [allRows, setAllRows] = useState<PromptSelectableRow[]>([]);

  useEffect(() => {
    let mounted = true;

    const fetchPromptList = async () => {
      try {
        const rows = await getPromptList();
        if (!mounted) return;
        setAllRows(rows);
      } catch (error) {
        console.error("프롬프트 목록 조회 실패", error);
        if (!mounted) return;
        setAllRows([]);
      } finally {
        if (mounted) {
        }
      }
    };

    void fetchPromptList();

    return () => {
      mounted = false;
    };
  }, [getPromptList]);
  

  const activePrompt = useMemo(
    () => allRows.find((row) => row.prompt_no === selectedPromptNo) ?? null,
    [allRows, selectedPromptNo],
  );

  const handleSelectRow = (promptNo: number) => {
    setSelectedPromptNo(promptNo);

    // 테이블 강조 상태 즉시 반영
    setAllRows((prev) =>
      prev.map((item) => ({
        ...item,
        SEL_YN: item.prompt_no === promptNo ? "Y" : "N",
      })),
    );
  };

  const handleApplyPrompt = () => {
    if (activePrompt) {
      onApplyPrompt({
        prompt_no: activePrompt.prompt_no,
        prompt_name: activePrompt.prompt_name,
        prompt_txt: activePrompt.prompt_txt,
        create_user: activePrompt.create_user,
      });
    }

    // 프롬프트 선택이 없어도, LLM 모델은 라디오 클릭 즉시 상위로 전달되므로 닫기 허용
    onClose();
  };

  return (
    <div className={styles.modalBackdrop} onClick={onClose} role="presentation">
      <section
        className={styles.modal}
        onClick={(event) => event.stopPropagation()}
        aria-modal="true"
        role="dialog"
      >
        <header className={styles.modalHeader}>
          <h3 className={styles.modalTitle}>프롬프트 목록</h3>
          <div className={styles.modalActions}>
            <button
              type="button"
              className={styles.actionButton}
              onClick={handleApplyPrompt}
            >
              사용 프롬프트 설정
            </button>
            <button type="button" className={styles.closeButton} onClick={onClose}>
              닫기
            </button>
          </div>
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
          <br/>
          <p className={styles.llmGuideTitle}>사용 LLM 모드 선택</p>
          <div className={styles.llmRadioGroup}>
            {LLM_MODE_OPTIONS.map((option) => (
              <label key={option.value} className={styles.llmRadioItem}>
                <input
                  type="radio"
                  name="llmMode"
                  value={option.value}
                  checked={selectedLlmMode === option.value}
                  onChange={() => onSelectLlmMode(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <br/>
          <p className={styles.llmGuideTitle}>사용 페르소나 선택</p>
          <div className={styles.llmRadioGroup}>
            {PERSONA_OPTIONS.map((option) => (
              <label key={option.value} className={styles.llmRadioItem}>
                <input
                  type="radio"
                  name="personaType"
                  value={option.value}
                  checked={selectedPersonaType === option.value}
                  onChange={() => onSelectPersonaType(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <p className={styles.llmGuideDesc}>
            선택한 LLM 모델과 모드, 페르소나, 선택한 프롬프트를 질문 요청과 함께 전달할 예정입니다.
          </p>
        </section>

        <div className={styles.tableWrap}>
          <table className={styles.promptTable}>
            <thead>
              <tr>
                <th>프롬프트 명</th>
                <th>프롬프트 내용</th>
                <th>작성자</th>
              </tr>
            </thead>
            <tbody>
              {allRows.map((row) => {
                const isActive = row.SEL_YN === "Y";

                return (
                  <tr
                    key={row.prompt_no}
                    className={isActive ? styles.activePromptRow : ""}
                    onClick={() => handleSelectRow(row.prompt_no)}
                  >
                    <td>{row.prompt_name}</td>
                    <td>{row.prompt_txt}</td>
                    <td>{row.create_user}</td>
                  </tr>
                );
              })}

              {allRows.length === 0 && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    등록된 프롬프트가 없습니다.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
