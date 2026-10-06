"use client";

import { useRef, useState } from "react";
import { ThumbsUp, ThumbsDown, FileQuestion } from "lucide-react";
import { updateMessageFeedback } from "@/services/chatApi";
import type { MessageFeedback } from "@/types/chatApi";
import styles from "./answer.module.css";

const OPTIONS = [
  { value: "도움됨", icon: ThumbsUp },
  { value: "틀림", icon: ThumbsDown },
  { value: "근거없음", icon: FileQuestion },
] as const;

export default function AnswerFeedback({ messageId, initialFeedback }: {
  messageId: number;
  initialFeedback?: MessageFeedback | null;
}) {
  const [feedback, setFeedback] = useState(initialFeedback ?? null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savingRef = useRef(false);

  async function saveFeedback(value: MessageFeedback) {
    if (savingRef.current || value === feedback) return;
    savingRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      await updateMessageFeedback(messageId, value);
      setFeedback(value);
    } catch {
      setError("피드백을 저장하지 못했습니다. 다시 눌러 주세요.");
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  }

  return (
    <div className={styles.feedback}>
      <div className={styles.feedbackOptions} role="group" aria-label="이 답변이 도움이 되었나요?" aria-busy={isSaving}>
        <span>이 답변이 도움이 되었나요?</span>
        {OPTIONS.map(({ value, icon: Icon }) => (
          <button key={value} type="button" data-feedback={value} aria-pressed={feedback === value}
            disabled={isSaving} onClick={() => void saveFeedback(value)}>
            <Icon size={15} aria-hidden="true" />{value}
          </button>
        ))}
        {isSaving && <span role="status">저장 중…</span>}
      </div>
      {error && <p className={styles.feedbackError} role="alert">{error}</p>}
    </div>
  );
}
