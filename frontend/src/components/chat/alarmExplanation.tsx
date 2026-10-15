"use client";

import type { AlarmAnalysis } from "./figureExplanationProvider";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamExplanation, type ManualSource } from "@/services/explanationApi";
import styles from "./figureExplanation.module.css";

type Turn = { role: "user" | "assistant"; content: string; sources?: ManualSource[] };
type FigureStatus = "loading" | "complete" | "error";
const INITIAL_QUESTION = "이 알람의 의미, 가능한 원인, 확인 순서와 조치 방법을 설명해 주세요.";

export default function AlarmExplanation({ id, alarm, onStatusChange }: {
  id: string; alarm: AlarmAnalysis;
  onStatusChange?: (id: string, status: FigureStatus) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [partial, setPartial] = useState<Turn | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState(INITIAL_QUESTION);
  const controller = useRef<AbortController | null>(null);
  const historyRef = useRef<Turn[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onStatusChange?.(id, busy ? "loading" : error ? "error" : "complete");
  }, [id, busy, error, onStatusChange]);

  const ask = useCallback(async (text: string) => {
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError(null);
    setPartial(null);
    setFailedQuestion(text);
    try {
      const data = await streamExplanation("/api/alarms/explain", {
        alarm, question: text,
        history: historyRef.current.slice(-6).map(turn => ({ role: turn.role, content: turn.content.slice(0, 4000) })),
      }, request.signal, result => {
        if (!request.signal.aborted) setPartial({ role: "assistant", content: result.answer, sources: result.sources });
      });
      if (request.signal.aborted) return;
      historyRef.current = [...historyRef.current, { role: "user", content: text }, { role: "assistant", content: data.answer, sources: data.sources }];
      setTurns(historyRef.current);
      setPartial(null);
      setQuestion("");
    } catch (cause) {
      if (request.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : "알람 분석을 불러오지 못했습니다. 다시 시도해 주세요.");
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setBusy(false);
      }
    }
  }, [alarm]);

  useEffect(() => {
    void ask(INITIAL_QUESTION);
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [ask]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns, partial, busy, error]);

  const displayedTurns: Turn[] = partial
    ? [...turns, { role: "user", content: failedQuestion }, partial]
    : turns;

  return (
    <div className={styles.alarmLayout}>

      <section className={styles.panel} aria-label="알람 분석 대화">
        <strong className={styles.title}>{alarm.machine_name} · {alarm.machine_code} · {alarm.alarm_type === "system" ? "시스템" : "Operate"} · {alarm.code}</strong>
        <p className={styles.alarmContext}>{alarm.message}<br /><small>장비에 연결된 매뉴얼을 검색해 답변합니다. 답변 아래에서 검색 근거를 확인할 수 있습니다.</small></p>
        <div className={styles.messages} ref={scrollRef} aria-live="polite">
          {displayedTurns.map((turn, index) => index === 0 && turn.content === INITIAL_QUESTION ? null : (
            <div key={index} className={turn.role === "user" ? styles.question : styles.answer}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
              {!!turn.sources?.length && <details className={styles.manualSources}>
                <summary>매뉴얼 검색 근거 {turn.sources.length}건</summary>
                {turn.sources.map(source => <details key={source.index}>
                  <summary>[근거 {source.index}] {source.document_name}{source.page ? ` · ${source.page}` : ""}</summary>
                  <p>{source.excerpt}</p>
                </details>)}
              </details>}
            </div>
          ))}
          {busy && !partial && turns.length > 0 && <div className={styles.question}>{failedQuestion}</div>}
          {busy && !partial && (
            <div className={styles.loading} role="status">
              <div className={styles.loadingLabel}>
                <span className={styles.spinner} aria-hidden="true" />
                <strong>{turns.length ? "매뉴얼을 검색해 후속 답변을 생성하고 있어요" : "매뉴얼에서 알람의 원인과 조치를 찾고 있어요"}</strong>
              </div>
              <span className={styles.loadingHint}>잠시만 기다려 주세요. 축소해도 계속 진행됩니다.</span>
              <div className={styles.skeleton} aria-hidden="true"><span /><span /><span /></div>
            </div>
          )}
          {error && <div role="alert"><p>{error}</p><button type="button" onClick={() => void ask(failedQuestion)}>다시 시도</button></div>}
        </div>
        <form className={styles.form} onSubmit={event => { event.preventDefault(); if (question.trim() && !busy) void ask(question.trim()); }}>
          <input aria-label="알람에 대한 후속 질문" placeholder="이 알람에 대해 이어서 질문하세요" value={question}
            maxLength={1000} disabled={busy} onChange={event => setQuestion(event.target.value)} />
          <button type="submit" className={styles.sendButton} disabled={busy || !question.trim()}>
            {busy && <span className={styles.spinner} aria-hidden="true" />}{busy ? "생성 중" : "질문"}
          </button>
        </form>
        <small className={styles.note}>화면을 이동해도 유지됩니다. 휴지통으로 삭제하거나 새로고침하면 초기화됩니다.</small>
      </section>
    </div>
  );
}

