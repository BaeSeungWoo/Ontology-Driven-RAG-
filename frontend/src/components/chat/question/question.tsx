"use client";

import { useState } from "react";
/**
 * 질문 입력 UI 파일.
 * - 사용자가 입력한 question과 선택된 llmModel을 payload로 만들어 상위(onSend)로 전달한다.
 * - 실제 API 호출은 하지 않고, 입력/submit 이벤트 처리만 담당한다.
 */
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import styles from "./question.module.css";

export type QuestionPayload = {
  question: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  // questioner: string;
  // promptNo: number;
  // promptName: string | null;
  // promptTxt: string | null;
};

type QuestionProps = {
  selectedLlmModel: LlmModel;
  selectedLlmMode: LlmMode;
  onSend: (payload: QuestionPayload) => void;
};

export default function Question({
  selectedLlmModel,
  selectedLlmMode,
  onSend,
}: QuestionProps) {
  // ============================================================
  // 상태(State)
  // - 질문 입력값과 전송 가능 여부를 관리한다.
  // ============================================================

  // In: 사용자 텍스트 입력
  // Out: 질문 입력창 값
  const [question, setQuestion] = useState("");

  // In: selectedPrompt prop
  // Out: 프롬프트 선택 여부
  // const hasPrompt = selectedPrompt !== null;

  // In: 질문/질문자/프롬프트 상태
  // Out: 전송 버튼 활성화 여부
  // const canSend = hasQuestion && hasQuestioner && hasPrompt;

  // ============================================================
  // 함수(Functions)
  // - 전송 이벤트를 payload로 정리해 상위 컴포넌트로 전달한다.
  // ============================================================

  /**
   * 질문 전송 처리
   * In: 현재 입력값(question) + 외부 상태(questioner, selectedPrompt, selectedLlm)
   * Out:
   * - onSend(payload) 호출
   * - 전송 후 입력창 초기화
   */
  const handleSend = () => {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;

    // 필수값이 없으면 전송하지 않는다.
    // if (!normalizedQuestion || !selectedPrompt) {
    //   return;
    // }

    onSend({
      question: normalizedQuestion,
      llmModel: selectedLlmModel,
      llmMode: selectedLlmMode,
      // questioner: questioner.trim(),
      // promptNo: selectedPrompt.prompt_no,
      // promptName: selectedPrompt.prompt_name ?? null,
      // promptTxt: selectedPrompt.prompt_txt ?? null,
    });

    setQuestion("");
  };

  /**
   * 폼 제출 처리
   * In: submit 이벤트(엔터/버튼)
   * Out: 기본 submit 동작 방지 + handleSend 실행
   */
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleSend();
  };

  // ============================================================
  // 최종 렌더(Render)
  // - 질문 입력창과 전송 버튼을 렌더한다.
  // ============================================================

  return (
    <form className="w-full" onSubmit={handleSubmit}>
      <div className="flex w-full items-center gap-[10px] rounded-full border border-[var(--chat-pane-border)] bg-[var(--chat-pane-bg)] px-[10px] py-2 pl-[22px] shadow-[0_1px_2px_var(--chat-shadow)]">
        <input
          id="question-input"
          type="text"
          className={styles.questionInput}
          placeholder={"무엇이든 물어보세요."}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button
          type="submit"
          className={styles.submitButton}
          aria-label={"질문 전송"}
          // disabled={!canSend}
        >
          {"↵"}
        </button>
      </div>
    </form>
  );
}
