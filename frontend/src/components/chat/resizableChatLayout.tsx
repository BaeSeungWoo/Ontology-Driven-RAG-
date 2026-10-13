"use client";

import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import styles from "./chat.module.css";

const MIN_HISTORY = 180;
const MIN_CITATION = 280;
const MIN_CENTER = 420;
// Two 12px grid gaps and 18px right padding.
const LAYOUT_SPACE = 42;

export default function ResizableChatLayout({ children, isCitationCollapsed, isWelcome }: {
  children: ReactNode;
  isCitationCollapsed: boolean;
  isWelcome: boolean;
}) {
  const layoutRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ side: "history" | "citation"; x: number; width: number } | null>(null);
  const [containerWidth, setContainerWidth] = useState(0);
  const [widths, setWidths] = useState({ history: 240, citation: 420 });
  const [isDragging, setIsDragging] = useState(false);

  useEffect(() => {
    const element = layoutRef.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setContainerWidth(element.getBoundingClientRect().width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const available = Math.max(MIN_HISTORY + MIN_CITATION, containerWidth - MIN_CENTER - LAYOUT_SPACE);
  const history = Math.min(widths.history, available - (isCitationCollapsed ? 44 : MIN_CITATION));
  const citation = isCitationCollapsed ? 44 : Math.min(widths.citation, available - history);
  const resize = (side: "history" | "citation", width: number) => {
    const min = side === "history" ? MIN_HISTORY : MIN_CITATION;
    const max = available - (side === "history" ? citation : history);
    setWidths(previous => ({ ...previous, [side]: Math.round(Math.max(min, Math.min(max, width))) }));
  };

  return (
    <div ref={layoutRef}
      className={`${styles.chatTypographyScope} ${isDragging ? styles.resizing : ""} tw-chat-layout ${isWelcome ? styles.welcomeLayout : isCitationCollapsed ? "tw-chat-layout-right-collapsed" : ""}`}
      style={{ "--history-width": `${history}px`, "--citation-width": `${citation}px` } as CSSProperties}
    >
      {children}
      {(["history", "citation"] as const).map(side => {
        if (side === "citation" && (isWelcome || isCitationCollapsed)) return null;
        const width = side === "history" ? history : citation;
        const label = side === "history" ? "질문 이력 너비 조절" : "인용 근거 너비 조절";
        return <div key={side} role="separator" tabIndex={0}
          aria-label={label} aria-orientation="vertical"
          aria-valuemin={side === "history" ? MIN_HISTORY : MIN_CITATION}
          aria-valuemax={available - (side === "history" ? citation : history)}
          aria-valuenow={width} aria-valuetext={`${width}px`}
          aria-describedby={`${side}-resize-hint`}
          className={`${styles.resizeHandle} ${side === "history" ? styles.historyResizeHandle : styles.citationResizeHandle}`}
          onPointerDown={event => {
            if (event.button !== 0) return;
            event.preventDefault();
            event.currentTarget.setPointerCapture(event.pointerId);
            dragRef.current = { side, x: event.clientX, width };
            setIsDragging(true);
          }}
          onPointerMove={event => {
            const drag = dragRef.current;
            if (!drag || !event.currentTarget.hasPointerCapture(event.pointerId)) return;
            resize(drag.side, drag.width + (event.clientX - drag.x) * (drag.side === "history" ? 1 : -1));
          }}
          onPointerUp={event => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onLostPointerCapture={() => { dragRef.current = null; setIsDragging(false); }}
          onPointerCancel={() => { dragRef.current = null; setIsDragging(false); }}
          onKeyDown={event => {
            if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
            event.preventDefault();
            resize(side, width + (event.key === "ArrowRight" ? 16 : -16) * (side === "history" ? 1 : -1));
          }}
        >
          <span className={styles.resizeGrip} aria-hidden="true" />
          <span id={`${side}-resize-hint`} role="tooltip" className={styles.resizeHint}>
            {side === "history" ? "질문 이력" : "인용 근거"} 너비를 조절하시려면<br />드래그해 주세요.
          </span>
        </div>;
      })}
    </div>
  );
}
