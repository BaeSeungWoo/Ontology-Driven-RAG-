"use client";

import { useState } from "react";
import { ArrowUp } from "lucide-react";

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
  // 내부 state
  // 기능/목적: 사용자가 작성 중인 질문 입력값과 전송 가능 여부를 관리한다.
  const [question, setQuestion] = useState("");

  const hasQuestion = question.trim().length > 0;
  const hasQuestioner = questioner.trim().length > 0;
  const hasPrompt = selectedPrompt !== null;
  const canSend = hasQuestion && hasQuestioner && hasPrompt;

  // 함수
  // 기능/목적: 필수값이 모두 있을 때 질문 payload를 만들고 상위 전송 로직을 호출한다.
  // Out: onSend 호출, 질문 입력값 초기화
  const handleSend = () => {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;
    if (!selectedPrompt) return;

    onSend({
      question: normalizedQuestion,
      llmModel: selectedLlmModel,
      llmMode: selectedLlmMode,
      questioner: questioner.trim(),
      prompt: selectedPrompt,
    });

    setQuestion("");
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    handleSend();
  };

  // render
  return (
    <form className="w-full" onSubmit={handleSubmit}>
      <div className="flex w-full items-center gap-2.5 rounded-full border border-(--chat-pane-border) bg-(--chat-pane-bg) px-[10px] py-2 pl-[22px] shadow-[0_1px_0_rgb(255_255_255_/_72%),0_6px_14px_rgb(37_68_104_/_24%)]">
        <input
          id="question-input"
          type="text"
          className={styles.questionInput}
          placeholder="무엇이든 물어보세요."
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button
          type="submit"
          className={styles.submitButton}
          aria-label="질문 전송"
          disabled={!canSend}
        >
          <ArrowUp className={styles.submitButtonIcon} aria-hidden="true" />
        </button>
      </div>
    </form>
  );
}
