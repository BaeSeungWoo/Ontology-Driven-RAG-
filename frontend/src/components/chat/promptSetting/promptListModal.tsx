"use client";

import { useEffect, useMemo, useState } from "react";
import { usePrompt } from "@/hooks/usePrompt";
import type { LlmModel, PromptRow, PromptSelectableRow } from "@/types/prompt";
import styles from "./promptSetting.module.css";

type PromptListModalProps = {
  onClose: () => void;
  selectedPrompt: PromptRow | null;
  selectedLlm: LlmModel;
  onSelectLlm: (model: LlmModel) => void;
  onApplyPrompt: (prompt: PromptRow) => void;
};

type LlmOption = { value: LlmModel; label: string };

const LLM_OPTIONS: LlmOption[] = [
  { value: "ollama", label: "Ollama" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "gemini", label: "Gemini" },
];

export default function PromptListModal({
  onClose,
  selectedPrompt,
  selectedLlm,
  onSelectLlm,
  onApplyPrompt,
}: PromptListModalProps) {
  const { getPromptList } = usePrompt();

  // 모달 내부 선택 상태(적용 버튼 누르기 전까지 임시 유지)
  const [selectedPromptNo, setSelectedPromptNo] = useState<number | null>(
    selectedPrompt?.prompt_no ?? null,
  );

  // 레거시 엔드포인트에서 받은 전체 프롬프트 목록
  const [allRows, setAllRows] = useState<PromptSelectableRow[]>([]);

  const [isLoading, setIsLoading] = useState(false);

  // 모달 최초 열림 시 상위 선택값을 내부 선택 상태로 동기화
  useEffect(() => {
    setSelectedPromptNo(selectedPrompt?.prompt_no ?? null);
  }, [selectedPrompt]);

  // 모달 열림(마운트) 시 목록 조회
  useEffect(() => {
    let mounted = true;

    const fetchPromptList = async () => {
      setIsLoading(true);
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
          setIsLoading(false);
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
    if (!activePrompt) return;

    onApplyPrompt({
      prompt_no: activePrompt.prompt_no,
      prompt_name: activePrompt.prompt_name,
      prompt_txt: activePrompt.prompt_txt,
      create_user: activePrompt.create_user,
    });

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
              disabled={!activePrompt}
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
            {LLM_OPTIONS.map((option) => (
              <label key={option.value} className={styles.llmRadioItem}>
                <input
                  type="radio"
                  name="llmModel"
                  value={option.value}
                  checked={selectedLlm === option.value}
                  onChange={() => onSelectLlm(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
          <p className={styles.llmGuideDesc}>
            선택한 LLM과 선택한 프롬프트를 질문 요청과 함께 전달할 예정입니다.
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

              {!isLoading && allRows.length === 0 && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    등록된 프롬프트가 없습니다.
                  </td>
                </tr>
              )}

              {isLoading && (
                <tr>
                  <td colSpan={3} className={styles.emptyCell}>
                    프롬프트 목록을 불러오는 중입니다.
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
