"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, LockKeyhole, CircleAlert } from "lucide-react";
import { useMachine } from "@/components/machineProvider";
import styles from "./machineSelect.module.css";

export default function MachineSelect({ value, onChange, disabled = false }: {
  value?: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}) {
  const { machines, status, refreshMachines } = useMachine();

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

  const assigned = value ? machines.find(machine => machine.machine_code === value)
    : machines.find(machine => machine.is_assigned);
  const isMaster = machines.some(machine => machine.is_main_server);
  const isUnready = (machine: typeof machines[number]) => (machine.is_main_server || machine.is_assigned) && !machine.can_select;
  const readinessLabel = (machine: typeof machines[number]) => machine.readiness === "no_documents" ? "준비 중 · 매뉴얼 미등록"
    : machine.readiness === "check_failed" ? "준비 상태 확인 실패" : "준비 중 · 검색 데이터 미구축";
  const sortedMachines = [...machines].sort((a, b) =>
    Number(b.can_select) - Number(a.can_select) || a.machine_code.localeCompare(b.machine_code, undefined, { numeric: true }));
  const placeholder = status === "loading" ? "장비 목록 불러오는 중"
    : status === "error" ? "장비 목록 조회 실패"
    : value === "ALL" ? "전체 장비" : value && !assigned ? `${value} · 미등록 장비`
    : machines.length === 0 ? "등록된 장비 없음" : isMaster ? "장비 선택 · 전체" : "할당된 장비 없음";

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
        disabled={disabled || status !== "ready" || machines.length === 0}
        onClick={() => {
          if (!isOpen) refreshMachines();
          setIsOpen(open => !open);
        }}
        onKeyDown={event => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            if (!isOpen) refreshMachines();
            setIsOpen(true);
          }
        }}
      >
        <span aria-hidden="true" className={`${styles.dot} ${assigned && isUnready(assigned) ? styles.unreadyDot : assigned?.can_select ? styles.assigned : ""}`} />
        <strong>{status === "ready" ? assigned?.machine_name ?? placeholder : placeholder}</strong>
        {status === "ready" && assigned && <span className={styles.spec}>{assigned.machine_controller} {assigned.machine_ver}</span>}
        <ChevronDown aria-hidden="true" size={13} className={styles.chevron} />
      </button>
      {isOpen && (
        <div className={styles.panel}>
          <div className={styles.heading}><strong>장비 목록</strong><span>{machines.length}대</span></div>
          <p id={`${listId}-guide`} className={styles.guide}><LockKeyhole size={13} aria-hidden="true" />{isMaster ? "검색 데이터가 준비된 장비만 선택할 수 있습니다. 장비를 변경하면 새 대화를 시작합니다." : "현재 IP에 할당된 장비만 선택할 수 있습니다."}</p>
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
                aria-selected={machine.machine_code === assigned?.machine_code} disabled={disabled || !machine.can_select}
                className={`${styles.option} ${isUnready(machine) ? styles.unready : ""}`}
                title={isUnready(machine) ? `${readinessLabel(machine)} · 선택 및 채팅을 사용할 수 없습니다.` : !machine.can_select ? "현재 IP에 할당되지 않아 선택할 수 없습니다." : undefined}
                onClick={() => {
                  if (machine.machine_code !== assigned?.machine_code) onChange(machine.machine_code);
                  setIsOpen(false); triggerRef.current?.focus();
                }}
              >
                <span aria-hidden="true" className={`${styles.dot} ${isUnready(machine) ? styles.unreadyDot : machine.can_select && machine.machine_code === assigned?.machine_code ? styles.assigned : ""}`} />
                <span className={styles.machineText}>
                  <strong>{machine.machine_name}</strong>
                  <span>{machine.machine_controller} {machine.machine_ver}</span>
                  {isUnready(machine) && <span className={styles.readiness}>{readinessLabel(machine)}</span>}
                </span>
                {isUnready(machine) ? <CircleAlert size={16} aria-hidden="true" />
                  : !machine.can_select ? <LockKeyhole size={14} aria-hidden="true" />
                  : machine.machine_code === assigned?.machine_code && <Check size={16} aria-hidden="true" />}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
