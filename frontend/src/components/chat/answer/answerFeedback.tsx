"use client";

import { useRef, useState } from "react";
import { ThumbsUp, ThumbsDown, Contrast, MessageSquareText, Check, X } from "lucide-react";
import { updateMessageFeedback, updateMessageReason } from "@/services/chatApi";
import type { MessageFeedback } from "@/types/chatApi";
import styles from "./answer.module.css";

const OPTIONS = [
  { value: "도움됨", icon: ThumbsUp },
  { value: "틀림", icon: ThumbsDown },
  { value: "부분도움", icon: Contrast },
] as const;

export default function AnswerFeedback({ messageId, initialFeedback, initialReason }: {
  messageId: number;
  initialFeedback?: MessageFeedback | null;
  initialReason?: string | null;
}) {
  const [feedback, setFeedback] = useState(initialFeedback ?? null);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savingRef = useRef(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState(initialReason ?? "");
  const hasReason = reason.trim().length > 0;
  const [draft, setDraft] = useState("");
  const [reasonError, setReasonError] = useState("");
  const [isSavingReason, setIsSavingReason] = useState(false);
  const reasonSavingRef = useRef(false);

  function openReason() {
    setDraft(reason);
    setReasonError("");
    dialogRef.current?.showModal();
  }

  async function saveReason() {
    if (!draft.trim() || reasonSavingRef.current) return;
    reasonSavingRef.current = true;
    setIsSavingReason(true);
    setReasonError("");
    const value = draft.trim();
    try {
      await updateMessageReason(messageId, value);
      setReason(value);
      dialogRef.current?.close();
    } catch {
      setReasonError("평가사유를 저장하지 못했습니다. 다시 시도해 주세요.");
    } finally {
      reasonSavingRef.current = false;
      setIsSavingReason(false);
    }
  }

  async function saveFeedback(value: MessageFeedback) {
    if (savingRef.current) return;
    const nextFeedback = value === feedback ? null : value;
    savingRef.current = true;
    setIsSaving(true);
    setError(null);
    try {
      await updateMessageFeedback(messageId, nextFeedback);
      setFeedback(nextFeedback);
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
        <button type="button" className={styles.reasonButton} data-completed={hasReason}
          title={hasReason ? "평가사유 확인 및 수정" : "평가사유 입력"}
          aria-haspopup="dialog" onClick={openReason}>
          <MessageSquareText size={15} aria-hidden="true" />
          평가
          {hasReason && <Check size={15} aria-hidden="true" />}
        </button>
        {isSaving && <span role="status">저장 중…</span>}
      </div>
      {error && <p className={styles.feedbackError} role="alert">{error}</p>}
      <dialog ref={dialogRef} className={styles.reasonDialog} aria-label="평가사유 입력"
        onCancel={event => { if (reasonSavingRef.current) event.preventDefault(); }}>
        <form onSubmit={event => { event.preventDefault(); void saveReason(); }}>
          <div className={styles.reasonHeader}>
            <h3>평가사유</h3>
            <button type="button" aria-label="닫기" disabled={isSavingReason} onClick={() => dialogRef.current?.close()}><X size={18} /></button>
          </div>
          <p>답변에서 도움이 된 점이나 개선이 필요한 점을 남겨주세요.</p>
          <textarea aria-label="평가사유" autoFocus required value={draft} disabled={isSavingReason}
            onChange={event => setDraft(event.target.value)} placeholder="답변에서 도움이 된 점이나 아쉬운 점을 입력해 주세요." rows={8} />
          {reasonError && <p className={styles.feedbackError} role="alert">{reasonError}</p>}
          <div className={styles.reasonActions}>
            <button type="button" disabled={isSavingReason} onClick={() => dialogRef.current?.close()}>취소</button>
            <button type="submit" disabled={isSavingReason || !draft.trim()}>{isSavingReason ? "저장 중…" : "확인"}</button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
