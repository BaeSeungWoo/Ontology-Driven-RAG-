import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamKnowledgeGraphAnswer } from "@/services/knowledgeGraphApi";
import type { Explanation } from "@/services/explanationApi";
import styles from "./knowledgeGraphPanel.module.css";

export default function KnowledgeGraphAnswer({ messageId, question, onClose }: {
  messageId: number; question: string; onClose: () => void;
}) {
  const [result, setResult] = useState<Explanation>({ answer: "", sources: [] });
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const ask = useCallback(async () => {
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError(null);
    setResult({ answer: "", sources: [] });
    try {
      const answer = await streamKnowledgeGraphAnswer(messageId, request.signal, partial => {
        if (!request.signal.aborted) setResult(partial);
      });
      if (!request.signal.aborted) setResult(answer);
    } catch (cause) {
      if (!request.signal.aborted) {
        setError(cause instanceof Error ? cause.message : "지식그래프 답변을 불러오지 못했습니다.");
      }
    } finally {
      if (controller.current === request) {
        controller.current = null;
        setBusy(false);
      }
    }
  }, [messageId]);

  useEffect(() => {
    void ask();
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [ask]);

  return <section className={styles.answerPanel} aria-label="지식그래프 기반 답변">
    <header className={styles.answerHeader}>
      <div><h3>지식그래프 기반 답변</h3><p>DHF8000 · FANUC 두 매뉴얼 근거</p></div>
      <button type="button" aria-label="지식그래프 답변 접기" onClick={onClose}><X size={18} aria-hidden="true" /></button>
    </header>
    <div className={styles.answerBody}>
      <p className={styles.answerQuestion}>{question}</p>
      {busy && <div className={styles.answerLoading} role="status">
        <LoaderCircle size={18} className={styles.spinner} aria-hidden="true" />
        <span>{result.answer ? "답변을 작성하고 있어요…" : "두 매뉴얼의 검색 근거로 답변을 만들고 있어요…"}</span>
      </div>}
      <div className={styles.answerText} aria-busy={busy}>
        <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]}>{result.answer}</ReactMarkdown>
      </div>
      {error && <div className={styles.answerError} role="alert">
        <p>{error}</p><button type="button" onClick={() => void ask()}>다시 시도</button>
      </div>}
      {result.sources.length > 0 && <details className={styles.answerSources}>
        <summary>답변에 전달한 매뉴얼 근거 {result.sources.length}개</summary>
        {result.sources.map(source => <details key={source.index}>
          <summary>[근거 {source.index}] {source.document_name}{source.page ? ` · p.${source.page}` : ""}</summary>
          <p>{source.excerpt}</p>
        </details>)}
      </details>}
    </div>
  </section>;
}
