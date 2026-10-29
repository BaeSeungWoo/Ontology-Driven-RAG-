"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { useMachine } from "@/components/machineProvider";
import type { FactoryId } from "@/services/api";
import styles from "./factorySelect.module.css";
import listStyles from "./machineSelect.module.css";

const factories: { id: FactoryId; name: string }[] = [
  { id: "yunam_origin", name: "연암(구)" },
  { id: "yunam", name: "연암" },
  { id: "yulkok", name: "율곡" },
  { id: "poongsan", name: "풍산" },
];

export default function FactorySelect({ disabled, onChange }: {
  disabled: boolean;
  onChange: (factory: FactoryId) => void;
}) {
  const { factoryId, status, refreshMachines } = useMachine();
  const [isOpen, setIsOpen] = useState(false);
  const controlRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!isOpen) return;
    listRef.current?.querySelector<HTMLButtonElement>('[aria-selected="true"]')?.focus();
    const closeOutside = (event: PointerEvent) => {
      if (!controlRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener("pointerdown", closeOutside);
    return () => document.removeEventListener("pointerdown", closeOutside);
  }, [isOpen]);

  return <div className={styles.control}>
    <div ref={controlRef} className={listStyles.control}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
      }}
      onKeyDown={event => {
        if (event.key === "Escape" && isOpen) {
          event.preventDefault();
          setIsOpen(false);
          triggerRef.current?.focus();
        }
      }}>
      <button ref={triggerRef} type="button" className={`${listStyles.trigger} ${styles.trigger}`}
        aria-label="공장 목록" aria-haspopup="listbox" aria-expanded={isOpen && !disabled}
        aria-controls={isOpen && !disabled ? listId : undefined} disabled={disabled}
        onClick={() => setIsOpen(open => !open)}
        onKeyDown={event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setIsOpen(true);
          }
        }}>
        <strong>{factories.find(factory => factory.id === factoryId)?.name}</strong>
        <ChevronDown size={13} aria-hidden="true" className={listStyles.chevron} />
      </button>
      {isOpen && !disabled && <div className={`${listStyles.panel} ${styles.panel}`}>
        <div className={listStyles.heading}><strong>공장 목록</strong><span>개발용</span></div>
        <div ref={listRef} id={listId} role="listbox" aria-label="공장" className={styles.list}
          onKeyDown={event => {
            if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
            event.preventDefault();
            const options = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('button'));
            const current = options.indexOf(document.activeElement as HTMLButtonElement);
            const index = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
              : event.key === "ArrowDown" ? Math.min(current + 1, options.length - 1) : Math.max(current - 1, 0);
            options[index]?.focus();
          }}>
          {factories.map(factory => <button key={factory.id} type="button" role="option"
            className={`${listStyles.option} ${styles.option}`} aria-selected={factoryId === factory.id}
            onClick={() => {
              setIsOpen(false);
              triggerRef.current?.focus();
              if (factory.id !== factoryId) onChange(factory.id);
            }}>
            <strong>{factory.name}</strong>
            {factoryId === factory.id && <Check size={15} aria-hidden="true" />}
          </button>)}
        </div>
      </div>}
    </div>
    {status === "error" && <button type="button" className={styles.retry} onClick={refreshMachines}>불러오기 실패 · 재시도</button>}
  </div>;
}
