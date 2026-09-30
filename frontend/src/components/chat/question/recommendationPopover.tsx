import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Lightbulb } from "lucide-react";
import styles from "./question.module.css";

export default function RecommendationPopover({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [requested, setRequested] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef}>
      <button
        ref={buttonRef}
        type="button"
        className={styles.recommendationButton}
        aria-label="추천 질문"
        title="추천 질문"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          setRequested(true);
          setOpen(value => !value);
        }}
      >
        <Lightbulb size={18} aria-hidden="true" />
      </button>
      <div id={panelId} className={styles.recommendationPopover} hidden={!open}>
        {requested ? children : null}
      </div>
    </div>
  );
}
