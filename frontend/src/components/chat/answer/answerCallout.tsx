import { useRef, useState, type ReactNode } from "react";
import { Check, ClipboardList, Copy, Lightbulb } from "lucide-react";
import styles from "./answer.module.css";

export default function AnswerCallout({ title, kind, children, isGenerating }: {
  title: string;
  kind: "summary" | "action";
  children: ReactNode;
  isGenerating: boolean;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");
  const Icon = kind === "summary" ? Lightbulb : ClipboardList;

  const copy = async (event: React.MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(bodyRef.current?.innerText ?? "");
      setCopyState("copied");
    } catch {
      setCopyState("failed");
    }
  };

  return (
    <section className={`${styles.answerCallout} ${kind === "summary" ? styles.summaryCallout : styles.actionCallout}`} aria-label={title}>
      <div className={styles.calloutHeader}>
        <span className={styles.calloutTitle}><Icon size={16} aria-hidden="true" />{title}</span>
        {kind === "action" && (
          <button type="button" className={styles.calloutCopy} onClick={copy} disabled={isGenerating} aria-label={`${title} 복사`}>
            {copyState === "copied" ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
            <span aria-live="polite">{copyState === "copied" ? "복사됨" : copyState === "failed" ? "복사 재시도" : "복사"}</span>
          </button>
        )}
      </div>
      <div ref={bodyRef} className={styles.calloutBody}>{children}</div>
      {copyState === "failed" && <p role="alert">복사하지 못했습니다. 다시 시도하거나 내용을 직접 선택해 주세요.</p>}
    </section>
  );
}
