"use client";

import { useMachine } from "@/components/machineProvider";

import { useEffect, useState } from "react";
import { Siren, X } from "lucide-react";
import styles from "./machineAlarmMonitor.module.css";
import { useAlarmExplanation } from "./chat/figureExplanationProvider";

type Snapshot = {
  machine: { code: string; name: string };
  collectedAt: string;
  alarms: { type: "system" | "operate"; code: string; message: string }[];
};
type AlarmEntry = {
  id: number;
  machine: Snapshot["machine"];
  alarm: Snapshot["alarms"][number];
  detectedAt: string;
  clearedAt: string | null;
};
const alarmKey = (machineCode: string, alarm: AlarmEntry["alarm"]) => JSON.stringify([machineCode, alarm.type, alarm.code, alarm.message]);
const alarmTypeLabel = (type: AlarmEntry["alarm"]["type"]) => type === "system" ? "시스템" : "Operate";

export default function MachineAlarmMonitor() {
  const { machineCode, status } = useMachine();
  if (status !== "ready" || !machineCode || machineCode === "ALL") return null;
  return <SelectedMachineAlarmMonitor key={machineCode} machineCode={machineCode} />;
}

function SelectedMachineAlarmMonitor({ machineCode }: { machineCode: string }) {
  const openExplanation = useAlarmExplanation();
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<AlarmEntry[]>([]);
  const [notices, setNotices] = useState<AlarmEntry[]>([]);
  const notice = notices[0];

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let reading = false;
    let previousAlarms = new Set<string>();
    let sequence = 0;
    async function poll() {
      if (controller.signal.aborted || reading) return;
      reading = true;
      try {
        const response = await fetch(`/local-api/alarms?machine_code=${encodeURIComponent(machineCode)}`,  {
          cache: "no-store",
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(8000)]),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || "알람 상태를 확인할 수 없습니다.");
        if (controller.signal.aborted) return;
        const next = data as Snapshot;
        if (next.machine.code !== machineCode) throw new Error("알람 응답의 장비 코드가 다릅니다.");
        const keys = new Set(next.alarms.map(alarm => alarmKey(next.machine.code, alarm)));
        if (keys.size !== previousAlarms.size || [...keys].some(key => !previousAlarms.has(key))) {
          const now = new Date().toISOString();
          const added: AlarmEntry[] = next.alarms.filter(alarm => !previousAlarms.has(alarmKey(next.machine.code, alarm)))
            .map(alarm => ({ id: ++sequence, machine: next.machine, alarm, detectedAt: now, clearedAt: null }));
          setEntries(current => {
            const history = current.map(item => item.clearedAt || keys.has(alarmKey(item.machine.code, item.alarm))
              ? item : { ...item, clearedAt: now });
            // 발생 중인 두 종류는 유지하고, 오래된 해제 이력부터 제거한다.
            const combined = [...added, ...history];
            return [...combined.filter(item => !item.clearedAt), ...combined.filter(item => item.clearedAt)].slice(0, 5);
          });
          setNotices(current => [...current.filter(item => keys.has(alarmKey(item.machine.code, item.alarm))), ...added]);
        }
        previousAlarms = keys;
        setSnapshot(next);
        setError("");
      } catch (err) {
        if (!controller.signal.aborted) {
          setNotices([]);
          setError(err instanceof Error ? err.message : "알람 상태를 확인할 수 없습니다.");
        }
      } finally {
        reading = false;
        if (!controller.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [machineCode]);

  const alarms = snapshot?.alarms ?? [];
  const stateLabel = (entry: AlarmEntry) => entry.clearedAt ? "해제" : error ? "상태 미확인" : "발생 중";
  function explain(entry: AlarmEntry) {
    setNotices([]);
    setOpen(false);
    openExplanation({ machine_code: entry.machine.code, machine_name: entry.machine.name,
      code: entry.alarm.code, message: entry.alarm.message, alarm_type: entry.alarm.type, detected_at: entry.detectedAt, cleared_at: entry.clearedAt });
  }
  return <aside className={styles.monitor} aria-label="장비 알람 모니터">
    {!open && notice && <div className={styles.noticeSlot} key={notice.id}>
      <section className={styles.notice} aria-label="새 알람 알림" role="button" tabIndex={0}
        onClick={() => explain(notice)}
        onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); explain(notice); } }}
        onAnimationEnd={event => {
          if (event.target === event.currentTarget) setNotices(current => current.filter(item => item.id !== notice.id));
        }}>
        <strong className={styles.noticeTitle}><Siren size={18} aria-hidden="true" />새 {alarmTypeLabel(notice.alarm.type)} 알람 · {notice.alarm.code}</strong>
        <p>{notice.machine.name} · {notice.machine.code}</p>
        <p className={styles.noticeMessage}>{notice.alarm.message || "알람 메시지가 없습니다."}</p>
        <time className={styles.collectedTime} dateTime={notice.detectedAt}>
          최초 수집 {new Date(notice.detectedAt).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour12: false })}
        </time>
      </section>
    </div>}
    {open && <section id="machine-alarm-panel" className={styles.popup} role="region" aria-labelledby="machine-alarm-title">
      <div className={styles.heading}>
        <strong id="machine-alarm-title">장비 알람 목록</strong>
        <button type="button" onClick={() => { setNotices([]); setOpen(false); }} aria-label="알람 목록 닫기">
          <X size={16} />
        </button>
      </div>
      <div className={styles.content}>
      {error && <p className={styles.error}>{error}</p>}
        <p className={styles.note}>최대 5건 · 발생 중인 알람을 유지하고 오래된 해제 이력부터 제거합니다.</p>
        {!entries.length && <p>{!snapshot ? "장비 알람 연결 대기 중" : "감지된 알람이 없습니다."}</p>}
        <ul className={styles.list}>{entries.map(entry => <li key={entry.id}>
          <button type="button" className={styles.entry} onClick={() => explain(entry)} aria-label={`${entry.alarm.code} 알람 원인과 조치 분석`}>
            <strong title={alarmTypeLabel(entry.alarm.type)}>{entry.alarm.code}<small className={styles.alarmType}>{alarmTypeLabel(entry.alarm.type)}</small></strong>
            <span className={styles.preview} title={entry.alarm.message}>{entry.alarm.message || "알람 메시지가 없습니다."}</span>
            <time className={styles.collectedTime} dateTime={entry.detectedAt}
              title={`이 화면에서 처음 수신한 시각: ${new Date(entry.detectedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`}>
              최초 수집 {new Date(entry.detectedAt).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul", hour12: false })}
            </time>
            <span className={styles.badge} data-cleared={Boolean(entry.clearedAt)}>{stateLabel(entry)}</span>
          </button>
        </li>)}</ul>
      </div>
    </section>}
    <button type="button" className={styles.siren} data-state={error ? "unknown" : alarms.length ? "active" : "idle"}
      aria-label={`알람 목록 ${open ? "접기" : "열기"}${error ? " · 상태 미확인" : alarms.length ? ` · 발생 중 ${alarms.length}건` : ""}`}
      aria-expanded={open} aria-controls="machine-alarm-panel"
      onClick={() => { setNotices([]); setOpen(value => !value); }}>
      <Siren size={26} aria-hidden="true" />
      {(error || alarms.length > 0) && <span className={styles.count}>{error ? "!" : alarms.length}</span>}
    </button>
    <span className={styles.srOnly} role="status">{error ? "장비 알람 확인 불가" : alarms.length ? alarms.map(alarm => `${alarmTypeLabel(alarm.type)} ${alarm.code}: ${alarm.message}`).join(" · ") : "수신 알람 없음"}</span>
  </aside>;
}
