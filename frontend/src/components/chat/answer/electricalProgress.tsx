import { useEffect, useState } from "react";
import { Check, ChevronDown, ChevronRight, FileSearch, CircuitBoard, ScanLine } from "lucide-react";
import type { ChatMetadata } from "@/types/chatApi";
import styles from "./answer.module.css";

function duration(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000));
  return seconds < 60 ? `${seconds}초` : `${Math.floor(seconds / 60)}분 ${seconds % 60}초`;
}

const stages = ["자료 준비", "도면 검색", "회로 판독", "답변 작성", "근거 검토", "마무리"];
function stageIndex(message: string) {
  if (/미리보기|매뉴얼/.test(message)) return 5;
  if (/검토|교정|대조|근거를 다시 읽|나누어 작성/.test(message)) return 4;
  if (/답변을 작성/.test(message)) return 3;
  if (/판독|연결 표기/.test(message)) return 2;
  if (/찾는/.test(message)) return 1;
  return 0;
}

export default function ElectricalProgress({ metadata, isGenerating, failed }: {
  metadata?: ChatMetadata;
  isGenerating: boolean;
  failed: boolean;
}) {
  const [mountedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [expanded, setExpanded] = useState(false);
  const [overviewExpanded, setOverviewExpanded] = useState(true);
  useEffect(() => {
    if (!isGenerating) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [isGenerating]);
  const history = metadata?.progress_history ?? [];
  const startedAt = metadata?.progress_started_at ?? history[0]?.at ?? mountedAt;
  const finishedAt = metadata?.progress_finished_at;
  const endAt = finishedAt ?? (isGenerating ? now : metadata?.progress_updated_at ?? history.at(-1)?.at ?? startedAt);
  const elapsed = duration(endAt - startedAt);
  const updatedAt = metadata?.progress_updated_at;
  const waitingForUpdate = now - (updatedAt ?? startedAt) > 30000;
  const current = metadata?.progress_message || "전기도면 QA 요청을 보내는 중";
  const completed = !isGenerating && !failed;
  const stage = completed ? stages.length : Math.max(0, ...history.map(step => stageIndex(step.message)), stageIndex(current));
  const pages = Array.from(new Set(history.flatMap(step =>
    /질문과 관련된/.test(step.message) ? step.detail?.match(/p\d+/g) ?? [] : [])));
  const identifiers = Array.from(new Set(history.flatMap(step =>
    (step.detail ?? "").split("\n")
      .flatMap(line => (line.match(/(?:부품|신호)\s+(?:식별|후보):\s*(.*)/)?.[1] ?? "")
        .split(/[,，]\s*/).map(value => value.trim()).filter(value => value && value !== "없음")))));
  const latestDetail = history.filter(step => step.detail).at(-1);
  const showOverview = !completed || overviewExpanded;
  const stepTimes = history.map((step, index) => Math.max(0,
    Math.min(history[index + 1]?.at ?? endAt, endAt) - Math.max(step.at, startedAt)));
  const stageTimes: (number | null)[] = stages.map(() => null);
  history.forEach((step, index) => {
    const group = stageIndex(step.message);
    stageTimes[group] = (stageTimes[group] ?? 0) + stepTimes[index];
  });
  const initialWait = Math.max(0, Math.min(history[0]?.at ?? endAt, endAt) - startedAt);
  if (initialWait > 0) stageTimes[0] = (stageTimes[0] ?? 0) + initialWait;
  const longestStage = stageTimes.some(time => time !== null && time > 0)
    ? stageTimes.indexOf(Math.max(...stageTimes.map(time => time ?? 0))) : -1;

  return (
    <div className={styles.electricalProgress}>
      {completed && <button type="button" className={styles.electricalProgressToggle} aria-expanded={overviewExpanded}
        onClick={event => { event.stopPropagation(); setOverviewExpanded(value => !value); }}>
        {overviewExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>분석 결과 · {elapsed} 소요</span>
      </button>}
      {showOverview && <section className={styles.electricalOverview} aria-label="전기도면 분석 진행 상황">
        <div className={styles.electricalOverviewHeader}>
          <span className={styles.electricalLiveState} data-delayed={isGenerating && waitingForUpdate || failed}>
            {isGenerating && !waitingForUpdate && <span className={styles.assistantThinkingSpinner} aria-hidden="true" />}
            {completed ? "분석 완료" : failed ? "작업 중단" : waitingForUpdate ? "응답 확인 필요" : "분석 진행 중"}
          </span>
          <span>{elapsed} {completed ? "소요" : "경과"}</span>
        </div>
        <div className={styles.electricalProgressStage} role="status" aria-live="polite">
          {completed ? "답변 생성에 사용한 검색·판독·검토 기록입니다." : failed ? "답변 생성을 마치지 못했습니다." : current}
        </div>
        <ol className={styles.electricalStages} aria-label="분석 단계">
          {stages.map((label, index) => <li key={label} data-state={index < stage ? "done" : index === stage ? "current" : "pending"}
            aria-current={index === stage ? "step" : undefined}>
            <span>{index < stage ? <Check size={12} aria-label="진행한 단계" /> : index + 1}</span>{label}
            <small className={styles.electricalStageTime}>
              {stageTimes[index] === null ? "기록 없음" : duration(stageTimes[index])}
              {isGenerating && index === stageIndex(current) ? " · 진행 중" : ""}
            </small>
          </li>)}
        </ol>
        <p className={styles.electricalNotice}>
          {longestStage >= 0 && <>가장 오래 걸린 단계: {stages[longestStage]} · {duration(stageTimes[longestStage]!)}. </>}
          진행 알림 수신 시각 기준이며, 반복 구간은 합산합니다.
        </p>
        <div className={styles.electricalFindings}>
          <article>
            <h4><FileSearch size={16} />관련 도면 <span>{pages.length ? `${pages.length}쪽` : isGenerating ? "검색 대기" : "기록 없음"}</span></h4>
            {pages.length ? <div className={styles.electricalChips}>{pages.map(page => <span key={page}>{page}</span>)}</div>
              : <p>{isGenerating ? "검색된 도면 페이지가 여기에 표시됩니다." : "저장된 도면 검색 기록이 없습니다."}</p>}
          </article>
          <article>
            <h4><CircuitBoard size={16} />부품·신호 <span>{identifiers.length ? `${identifiers.length}개 후보` : isGenerating ? "확인 대기" : "기록 없음"}</span></h4>
            {identifiers.length ? <><div className={styles.electricalChips}>{identifiers.slice(0, 8).map(id => <span key={id}>{id}</span>)}</div>
              {identifiers.length > 8 && <details onClick={event => event.stopPropagation()}><summary>나머지 {identifiers.length - 8}개 보기</summary>
                <div className={styles.electricalChips}>{identifiers.slice(8).map(id => <span key={id}>{id}</span>)}</div></details>}</>
              : <p>{isGenerating ? "검색·판독한 식별자가 여기에 모입니다." : "저장된 부품·신호 식별자 기록이 없습니다."}</p>}
          </article>
        </div>
        {latestDetail && <div className={styles.electricalLatestResult}>
          <h4><ScanLine size={16} />{completed ? "마지막 처리 기록" : "최근 처리 결과"} <span>{completed ? "당시 작업 기록" : "검토 중 자료"}</span></h4>
          <p>{latestDetail.detail}</p>
        </div>}
        {!completed && <p className={styles.electricalConnectionStatus}>
          {failed ? "중단 전까지 수집한 자료입니다. 최종 답변이 아닙니다." : waitingForUpdate
            ? "30초 이상 새 응답이 없습니다. 서버 작업이 계속되는지 아직 확인할 수 없습니다."
            : updatedAt ? `서버 응답 ${duration(now - updatedAt)} 전 · 연결 유지 중` : "서버의 첫 응답을 기다리고 있습니다."}
        </p>}
        {!failed && <p className={styles.electricalNotice}>{completed
          ? "검색·판독 후보가 모두 최종 답변에 인용되는 것은 아닙니다. 실제로 인용된 근거는 답변의 인용 표시에서 확인하세요."
          : "중간 자료는 최종 검증 전입니다. 근거 검토에는 수 분이 걸릴 수 있습니다."}</p>}
      </section>}
      <button type="button" className={styles.electricalProgressToggle} aria-expanded={expanded}
        onClick={event => { event.stopPropagation(); setExpanded(value => !value); }}>
        {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span>전체 작업 이력 {history.length}개</span>
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
              <span className={styles.electricalStepTime}>{duration(stepTimes[index])}
                {isGenerating && index === history.length - 1 ? " · 진행 중" : ""}</span>
            </li>
          ))}
          {!isGenerating && <li>
            <span>{failed ? "답변 생성이 중단되었습니다." : "답변 생성이 완료되었습니다."}</span></li>}
        </ol>
      )}
    </div>
  );
}
