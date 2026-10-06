"use client";

import Image from "next/image";
import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import axios from "axios";
import api from "@/services/api";
import styles from "./figureExplanation.module.css";

type Turn = { role: "user" | "assistant"; content: string };
export type FigureStatus = "loading" | "complete" | "error";
const INITIAL_QUESTION = "이 그림의 목적과 기호, 선, 화살표의 의미를 읽는 순서대로 쉽게 설명해 주세요.";

export default function FigureExplanation({ messageId, assetPath, imageUrl, label, onStatusChange }: {
  messageId: number; assetPath: string; imageUrl: string; label: string;
  onStatusChange?: (id: string, status: FigureStatus) => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [failedQuestion, setFailedQuestion] = useState(INITIAL_QUESTION);
  const controller = useRef<AbortController | null>(null);
  const historyRef = useRef<Turn[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    onStatusChange?.(`${messageId}:${assetPath}`, busy ? "loading" : error ? "error" : "complete");
  }, [messageId, assetPath, busy, error, onStatusChange]);

  const ask = useCallback(async (text: string) => {
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError(null);
    setFailedQuestion(text);
    try {
      const { data } = await api.post<{ answer: string }>("/api/figures/explain", {
        model: "vllm_config", message_id: messageId, asset_path: assetPath, question: text,
        history: historyRef.current.slice(-6).map(turn => ({ ...turn, content: turn.content.slice(0, 4000) })),
      }, { signal: request.signal, timeout: 120_000 });
      if (request.signal.aborted) return;
      historyRef.current = [...historyRef.current, { role: "user", content: text }, { role: "assistant", content: data.answer }];
      setTurns(historyRef.current);
      setQuestion("");
    } catch (cause) {
      if (request.signal.aborted) return;
      const detail = axios.isAxiosError(cause) ? cause.response?.data?.detail : undefined;
      setError(typeof detail === "string" ? detail : "그림 설명을 불러오지 못했습니다. 다시 시도해 주세요.");
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setBusy(false);
      }
    }
  }, [messageId, assetPath]);

  useEffect(() => {
    void ask(INITIAL_QUESTION);
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [ask]);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns, busy, error]);

  return (
    <div className={styles.layout}>
      <div className={styles.image}><Image src={imageUrl} alt={label} width={920} height={700} unoptimized /></div>
      <section className={styles.panel} aria-label="그림 설명 대화">
        <strong className={styles.title}>그림 풀어서 설명 · Qwen3-VL</strong>
        <div className={styles.messages} ref={scrollRef} aria-live="polite">
          {turns.map((turn, index) => index === 0 && turn.content === INITIAL_QUESTION ? null : (
            <div key={index} className={turn.role === "user" ? styles.question : styles.answer}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{turn.content}</ReactMarkdown>
            </div>
          ))}
          {busy && turns.length > 0 && <div className={styles.question}>{failedQuestion}</div>}
          {busy && (
            <div className={styles.loading} role="status">
              <div className={styles.loadingLabel}>
                <span className={styles.spinner} aria-hidden="true" />
                <strong>{turns.length ? "질문에 대한 답변을 생성하고 있어요" : "그림을 분석하고 설명을 생성하고 있어요"}</strong>
              </div>
              <span className={styles.loadingHint}>잠시만 기다려 주세요. 축소해도 계속 진행됩니다.</span>
              <div className={styles.skeleton} aria-hidden="true"><span /><span /><span /></div>
            </div>
          )}
          {error && <div role="alert"><p>{error}</p><button type="button" onClick={() => void ask(failedQuestion)}>다시 시도</button></div>}
        </div>
        <form className={styles.form} onSubmit={event => { event.preventDefault(); if (question.trim() && !busy) void ask(question.trim()); }}>
          <input aria-label="그림에 대한 후속 질문" placeholder="이 그림에서 궁금한 점을 물어보세요" value={question}
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
