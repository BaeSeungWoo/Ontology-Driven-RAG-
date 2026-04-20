"use client";

import { useState } from "react";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PromptRow } from "@/types/prompt";
import styles from "./question.module.css";

export type QuestionPayload = {
  question: string;
  questioner: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  prompt: PromptRow;
};

type QuestionProps = {
  questioner: string;
  selectedLlmModel: LlmModel;
  selectedLlmMode: LlmMode;
  selectedPrompt: PromptRow | null;
  onSend: (payload: QuestionPayload) => void;
};

export default function Question({
  questioner,
  selectedLlmModel,
  selectedLlmMode,
  selectedPrompt,
  onSend,
}: QuestionProps) {
  // =========================
  // state
  // =========================
  const [question, setQuestion] = useState("");

  const hasQuestion = question.trim().length > 0;
  const hasQuestioner = questioner.trim().length > 0;
  const hasPrompt = selectedPrompt !== null;
  const canSend = hasQuestion && hasQuestioner && hasPrompt;

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 현재 입력값을 질문 payload로 구성해 상위로 전달한다.
   * 목적: 질문 전송에 필요한 필수값을 검증하고, 정상 전송 후 입력창을 초기화한다.
   * In: question, questioner, selectedLlmModel, selectedLlmMode, selectedPrompt
   * Out: onSend(payload) 호출, question 초기화
   */
  const handleSend = () => {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;

    if (!normalizedQuestion || !selectedPrompt) {
      return;
    }

    onSend({
      question: normalizedQuestion,
      llmModel: selectedLlmModel,
      llmMode: selectedLlmMode,
      questioner: questioner.trim(),
      prompt: selectedPrompt,
    });

    setQuestion("");
  };

  /**
   * 기능: 폼 submit 이벤트를 처리한다.
   * 목적: 브라우저 기본 submit 동작을 막고 내부 전송 로직(handleSend)만 실행한다.
   * In: submit event
   * Out: preventDefault + handleSend()
   */
  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleSend();
  };

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return (
    <form className="w-full" onSubmit={handleSubmit}>
      <div className="flex w-full items-center gap-2.5 rounded-full border border-(--chat-pane-border) bg-(--chat-pane-bg) px-[10px] py-2 pl-[22px] shadow-[0_1px_2px_var(--chat-shadow)]">
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
          disabled={!canSend}
        >
          {"↵"}
        </button>
      </div>
    </form>
  );
}
