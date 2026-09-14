"use client";

import { useRef, useState } from "react";
import VoiceInput from "./voiceInput";

import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import type { PromptRow } from "@/types/prompt";

import styles from "./question.module.css";

export type QuestionPayload = {
  question: string;
  questioner: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  personaType: PersonaType;
  prompt: PromptRow;
};

type QuestionProps = {
  questioner: string;
  selectedLlmModel: LlmModel;
  selectedLlmMode: LlmMode;
  selectedPersonaType: PersonaType;
  selectedPrompt: PromptRow | null;
  isBusy?: boolean;
  onSend: (payload: QuestionPayload) => Promise<boolean>;
};

export default function Question({
  questioner,
  selectedLlmModel,
  selectedLlmMode,
  selectedPersonaType,
  selectedPrompt,
  onSend,
  isBusy = false,
}: QuestionProps) {
  // 내부 state
  // 기능/목적: 사용자가 작성 중인 질문 입력값과 전송 가능 여부를 관리한다.
  const [question, setQuestion] = useState("");
  const [voiceActive, setVoiceActive] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [sendError, setSendError] = useState("");
  const submitting = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = isBusy || isSubmitting;
  const voiceContext = JSON.stringify([questioner, selectedPrompt?.prompt_no, selectedLlmModel, selectedLlmMode, selectedPersonaType]);

  const hasQuestion = question.trim().length > 0;
  const hasQuestioner = questioner.trim().length > 0;
  const hasPrompt = selectedPrompt !== null;
  const canSend = hasQuestion && hasQuestioner && hasPrompt && !voiceActive && !busy;

  // 함수
  // 기능/목적: 필수값이 모두 있을 때 질문 payload를 만들고 상위 전송 로직을 호출한다.
  // Out: onSend 호출, 질문 입력값 초기화
  const handleSend = async () => {
    if (!canSend || submitting.current) return;
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return;
    if (!selectedPrompt) return;

    submitting.current = true;
    setIsSubmitting(true);
    setSendError("");
    try {
      const success = await onSend({
        question: normalizedQuestion,
        llmModel: selectedLlmModel,
        llmMode: selectedLlmMode,
        personaType: selectedPersonaType,
        questioner: questioner.trim(),
        prompt: selectedPrompt,
      });
      if (success) setQuestion("");
      else setSendError("질문을 전송하지 못했습니다. 입력 내용은 유지됩니다.");
    } catch {
      setSendError("질문 전송 중 오류가 발생했습니다. 입력 내용은 유지됩니다.");
    } finally {
      submitting.current = false;
      setIsSubmitting(false);
    }
  };

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void handleSend();
  };

  // render
  return (
    <form className="w-full" onSubmit={handleSubmit}>
      <VoiceInput key={voiceContext} disabled={busy} onActiveChange={setVoiceActive} onComplete={text => {
        setQuestion(previous => [previous.trim(), text.trim()].filter(Boolean).join(" "));
        inputRef.current?.focus();
      }} />
      {sendError && <p role="alert" className={styles.voiceError}>{sendError}</p>}
      <div className="flex w-full items-center gap-2.5 rounded-full border border-(--chat-pane-border) bg-(--chat-pane-bg) px-[10px] py-2 pl-[22px] shadow-[0_1px_0_rgb(255_255_255_/_72%),0_6px_14px_rgb(37_68_104_/_24%)]">
        <input
          id="question-input"
          ref={inputRef}
          type="text"
          className={styles.questionInput}
          placeholder="무엇이든 물어보세요."
          value={question}
          readOnly={voiceActive || busy}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <button
          type="submit"
          className={styles.submitButton}
          aria-label="질문 전송"
          disabled={!canSend}
        >
          <span aria-hidden="true">↑</span>
        </button>
      </div>
    </form>
  );
}
