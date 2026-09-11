"use client";

import { useEffect, useRef, useState } from "react";
import { Mic } from "lucide-react";
import { VoiceSession, voiceError, type VoiceState } from "@/services/voiceInput";
import styles from "./question.module.css";

type Props = {
  disabled: boolean;
  onComplete: (text: string) => void;
  onActiveChange: (active: boolean) => void;
};

export default function VoiceInput({ disabled, onComplete, onActiveChange }: Props) {
  const [state, setState] = useState<VoiceState | null>(null);
  const [error, setError] = useState("");
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const session = useRef<VoiceSession | null>(null);
  const mounted = useRef(true);
  const scanning = useRef(false);
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    mounted.current = true;
    const cancel = () => { session.current?.cancel(); session.current = null; onActiveChange(false); };
    window.addEventListener("pagehide", cancel);
    return () => { mounted.current = false; window.removeEventListener("pagehide", cancel); cancel(); };
  }, [onActiveChange]);

  const start = () => {
    if (disabled || session.current || scanning.current) return;
    setError(""); onActiveChange(true);
    let enumerated = false;
    const current = new VoiceSession({
      onState: next => {
        if (session.current !== current) return;
        setState(next);
        if (next.phase === "recording" && !enumerated) {
          enumerated = true;
          void navigator.mediaDevices.enumerateDevices().then(items => {
            if (session.current === current) setDevices(items.filter(d => d.kind === "audioinput"));
          }).catch(() => {});
        }
      },
      onComplete: text => {
        if (session.current !== current) return;
        session.current = null; setState(null); onActiveChange(false); onComplete(text);
      },
      onError: message => {
        if (session.current !== current) return;
        session.current = null; setState(null); onActiveChange(false); setError(message);
      },
    });
    session.current = current;
    void current.start(deviceId);
  };
  const cancel = () => {
    const current = session.current; session.current = null; current?.cancel();
    setState(null); setError(""); onActiveChange(false);
  };
  const refreshDevices = async () => {
    if (disabled || session.current || scanning.current) return;
    scanning.current = true; setIsScanning(true); onActiveChange(true); setError("");
    let stream: MediaStream | undefined;
    try {
      if (!window.isSecureContext || !navigator.mediaDevices) throw new Error("마이크 목록은 HTTPS 또는 localhost에서 사용할 수 있습니다.");
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const items = await navigator.mediaDevices.enumerateDevices();
      if (mounted.current) setDevices(items.filter(d => d.kind === "audioinput"));
    } catch (error) { if (mounted.current) setError(voiceError(error)); }
    finally {
      stream?.getTracks().forEach(track => track.stop());
      scanning.current = false;
      if (mounted.current) { setIsScanning(false); onActiveChange(false); }
    }
  };

  return (
    <div className={styles.voiceArea}>
      <div className={styles.voiceToolbar}>
        {!state ? <button type="button" className={styles.voiceButton} disabled={disabled || isScanning} onClick={start} aria-label="음성으로 질문 입력">
          <Mic size={16} aria-hidden="true" /> 음성 입력
        </button> : <>
          <span role="status">{state.phase === "connecting" ? "마이크 연결 중…" : state.phase === "recording" ? "듣고 있습니다" : "마지막 음성을 처리하고 있습니다…"}</span>
          <meter aria-label="마이크 입력 음량" min={0} max={1} value={state.level} />
          <button type="button" className={styles.voiceButton} disabled={state.phase !== "recording"} onClick={() => void session.current?.stop()}>완료</button>
          <button type="button" className={styles.voiceButton} onClick={cancel}>취소</button>
        </>}
        {!state && <details className={styles.microphoneSettings}>
          <summary>마이크 선택</summary>
          <select aria-label="사용할 마이크" value={deviceId} disabled={disabled} onChange={e => setDeviceId(e.target.value)}>
            <option value="">시스템 기본 마이크</option>
            {devices.filter(d => d.deviceId !== "default").map((d, i) => <option key={d.deviceId || i} value={d.deviceId}>{d.label || `마이크 ${i + 1}`}</option>)}
          </select>
          <button type="button" className={styles.voiceButton} disabled={disabled || isScanning} onClick={() => void refreshDevices()}>{isScanning ? "마이크 확인 중…" : "목록 새로고침"}</button>
        </details>}
      </div>
      {state && <div className={styles.voicePreview} aria-label="음성 인식 미리보기">
        <span>{state.committed}</span>{" "}<span className={styles.voicePartial}>{state.partial}</span>
        {!state.committed && !state.partial && <span className={styles.voicePartial}>말씀하신 내용이 여기에 표시됩니다.</span>}
        <small>완료 후 질문을 확인하고 전송해 주세요.</small>
      </div>}
      {error && <p role="alert" className={styles.voiceError}>{error}</p>}
    </div>
  );
}
