import { useEffect, useId, useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import styles from "./reportTheme.module.css";

export const TEST_REPORT_DATE = "2026-08-20";

export function yesterdayInKorea(now = new Date()) {
  const koreaDate = new Date(now.getTime() + 9 * 60 * 60 * 1000);
  koreaDate.setUTCDate(koreaDate.getUTCDate() - 1);
  return koreaDate.toISOString().slice(0, 10);
}

export default function ReportDatePicker({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const max = yesterdayInKorea();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(value.slice(0, 7));
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const [year, monthNumber] = month.split("-").map(Number);
  const firstWeekday = new Date(Date.UTC(year, monthNumber - 1, 1)).getUTCDay();
  const days = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();

  useEffect(() => {
    if (!open) return;
    const closeOutside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [open]);

  const moveMonth = (offset: number) => {
    setMonth(new Date(Date.UTC(year, monthNumber - 1 + offset, 1)).toISOString().slice(0, 7));
  };

  return (
    <div
      ref={root}
      className={styles.reportDate}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          setOpen(false);
          trigger.current?.focus();
        }
      }}
      onBlur={(event) => {
        if (event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <span>기준일</span>
      <button
        ref={trigger}
        type="button"
        className={styles.dateTrigger}
        aria-label={`기준일 ${value}, 달력 열기`}
        aria-expanded={open}
        aria-controls={id}
        aria-haspopup="dialog"
        onClick={() => {
          if (!open) setMonth(value.slice(0, 7));
          setOpen(!open);
        }}
      >
        {value}<CalendarDays size={16} aria-hidden="true" />
      </button>
      {open && (
        <div id={id} className={styles.calendar} role="dialog" aria-label="리포트 기준일 선택">
          <div className={styles.calendarHeading}>
            <button type="button" aria-label="이전 달" onClick={() => moveMonth(-1)}><ChevronLeft size={18} /></button>
            <strong aria-live="polite">{year}년 {monthNumber}월</strong>
            <button type="button" aria-label="다음 달" disabled={month >= max.slice(0, 7)} onClick={() => moveMonth(1)}><ChevronRight size={18} /></button>
          </div>
          <div className={styles.calendarGrid}>
            {["일", "월", "화", "수", "목", "금", "토"].map(day => <span key={day}>{day}</span>)}
            {Array.from({ length: firstWeekday }, (_, i) => <span key={`empty-${i}`} />)}
            {Array.from({ length: days }, (_, i) => {
              const day = `${month}-${String(i + 1).padStart(2, "0")}`;
              return (
                <button
                  key={day}
                  type="button"
                  aria-label={day}
                  aria-pressed={day === value}
                  disabled={day > max}
                  onClick={() => { setOpen(false); trigger.current?.focus(); onChange(day); }}
                >{i + 1}</button>
              );
            })}
          </div>
          <p>{max}까지 선택할 수 있습니다.</p>
        </div>
      )}
    </div>
  );
}
