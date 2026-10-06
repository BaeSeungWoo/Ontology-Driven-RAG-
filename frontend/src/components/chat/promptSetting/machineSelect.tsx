"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, LockKeyhole } from "lucide-react";
import api from "@/services/api";
import styles from "./machineSelect.module.css";

type Machine = {
  machine_code: string;
  machine_name: string;
  machine_controller: string;
  machine_ver: string;
  is_assigned: boolean;
};

export default function MachineSelect() {
  const [machines, setMachines] = useState<Machine[]>([]);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");

  const [isOpen, setIsOpen] = useState(false);
  const controlRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!isOpen) return;
    const list = listRef.current;
    (list?.querySelector<HTMLButtonElement>("button:not(:disabled)") ?? list)?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!controlRef.current?.contains(event.target as Node)) setIsOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [isOpen]);

  useEffect(() => {
    let active = true;
    api.get<Machine[]>("/api/prompts/machines").then(response => {
      if (!active) return;
      setMachines(response.data);
      setStatus("ready");
    }).catch(() => {
      if (active) setStatus("error");
    });
    return () => { active = false; };
  }, []);

  const assigned = machines.find(machine => machine.is_assigned);
  const sortedMachines = [...machines].sort((a, b) => Number(b.is_assigned) - Number(a.is_assigned));
  const placeholder = status === "loading" ? "장비 목록 불러오는 중"
    : status === "error" ? "장비 목록 조회 실패"
    : machines.length === 0 ? "등록된 장비 없음" : "할당된 장비 없음";

  return (
    <div ref={controlRef} className={styles.control}
      onBlur={event => {
        if (!event.currentTarget.contains(event.relatedTarget)) setIsOpen(false);
      }}
      onKeyDown={event => {
        if (event.key === "Escape" && isOpen) {
          event.preventDefault();
          setIsOpen(false);
          triggerRef.current?.focus();
        }
      }}
    >
      <button ref={triggerRef} type="button" className={styles.trigger}
        aria-label="장비 목록" aria-haspopup="listbox" aria-expanded={isOpen}
        aria-controls={isOpen ? listId : undefined}
        disabled={status !== "ready" || machines.length === 0}
        onClick={() => setIsOpen(open => !open)}
        onKeyDown={event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setIsOpen(true);
          }
        }}
      >
        <span aria-hidden="true" className={`${styles.dot} ${assigned ? styles.assigned : ""}`} />
        <strong>{assigned?.machine_name ?? placeholder}</strong>
        {assigned && <span className={styles.spec}>{assigned.machine_controller} {assigned.machine_ver}</span>}
        <ChevronDown aria-hidden="true" size={13} className={styles.chevron} />
      </button>
      {isOpen && (
        <div className={styles.panel}>
          <div className={styles.heading}><strong>장비 목록</strong><span>{machines.length}대</span></div>
          <p id={`${listId}-guide`} className={styles.guide}><LockKeyhole size={13} aria-hidden="true" />현재 IP에 할당된 장비만 선택할 수 있습니다.</p>
          <div ref={listRef} id={listId} role="listbox" aria-label="장비" aria-describedby={`${listId}-guide`}
            tabIndex={-1} className={styles.list}
            onKeyDown={event => {
              if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const options = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
              const current = options.indexOf(document.activeElement as HTMLButtonElement);
              const index = event.key === "Home" ? 0 : event.key === "End" ? options.length - 1
                : event.key === "ArrowDown" ? Math.min(current + 1, options.length - 1) : Math.max(current - 1, 0);
              options[index]?.focus();
            }}
          >
            {sortedMachines.map(machine => (
              <button type="button" role="option" key={machine.machine_code}
                aria-selected={machine.is_assigned} disabled={!machine.is_assigned}
                className={styles.option}
                title={!machine.is_assigned ? "현재 IP에 할당되지 않아 선택할 수 없습니다." : undefined}
                onClick={() => { setIsOpen(false); triggerRef.current?.focus(); }}
              >
                <span aria-hidden="true" className={`${styles.dot} ${machine.is_assigned ? styles.assigned : ""}`} />
                <span className={styles.machineText}><strong>{machine.machine_name}</strong><span>{machine.machine_controller} {machine.machine_ver}</span></span>
                {machine.is_assigned ? <Check size={16} aria-hidden="true" /> : <LockKeyhole size={14} aria-hidden="true" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
