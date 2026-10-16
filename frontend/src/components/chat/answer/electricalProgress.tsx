import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { ChatMetadata } from "@/types/chatApi";
import styles from "./answer.module.css";

function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return seconds < 60 ? `${seconds}초` : `${Math.floor(seconds / 60)}분 ${seconds % 60}초`;
}

export default function ElectricalProgress({ metadata, isGenerating, failed }: {
  metadata?: ChatMetadata;
  isGenerating: boolean;
  failed: boolean;
}) {
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(isGenerating || failed);
  useEffect(() => {
    if (!isGenerating) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [isGenerating]);
  const startedAt = metadata?.progress_started_at ?? mountedAt;
  const finishedAt = metadata?.progress_finished_at;
  const elapsed = duration((finishedAt ?? now) - startedAt);
  const updatedAt = metadata?.progress_updated_at;
  const waitingForUpdate = now - (updatedAt ?? startedAt) > 30000;
  const history = metadata?.progress_history ?? [];
  const current = metadata?.progress_message || "전기도면 QA 요청을 보내는 중";

  return (
    <div className={styles.electricalProgress}>
      <button type="button" className={styles.electricalProgressToggle} aria-expanded={expanded}
        onClick={event => { event.stopPropagation(); setExpanded(value => !value); }}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {isGenerating && <span className={styles.assistantThinkingSpinner} aria-hidden="true" />}
        <span>{elapsed} 동안 작업{isGenerating ? " 중" : failed ? " · 중단됨" : "함"}</span>
        <span>작업 이력 {history.length}개</span>
      </button>
      {expanded && (
        <ol className={styles.electricalProgressHistory} aria-label="전기도면 작업 이력">
          {history.map((step, index) => (
            <li key={`${step.at}-${index}`}>
              {step.detail ? (
                <details className={styles.electricalProgressStep} onClick={event => event.stopPropagation()}>
                  <summary>{step.message}<span className={styles.electricalProgressHint}>처리 내용</span></summary>
                  <div className={styles.electricalProgressResult}>{step.detail}</div>
                </details>
              ) : <span>{step.message}</span>}
            </li>
          ))}
          {!isGenerating && <li>
            <span>{failed ? "답변 생성이 중단되었습니다." : "답변 생성이 완료되었습니다."}</span></li>}
        </ol>
      )}
      {isGenerating && (
        <>
          <div className={styles.electricalProgressStage} role="status" aria-live="polite">{current}…</div>
          <p className={styles.electricalProgressDetail}>
            <span>{waitingForUpdate ? "서버 상태 갱신이 지연되고 있습니다." : updatedAt ? `서버 응답 확인: ${duration(now - updatedAt)} 전` : "서버의 첫 응답을 기다리고 있습니다."}</span>
            <span>도면 판독과 근거 검토에는 수 분이 걸릴 수 있습니다.</span>
          </p>
        </>
      )}
    </div>
  );
}
