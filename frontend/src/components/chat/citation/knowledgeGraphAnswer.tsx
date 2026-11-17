import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronUp, LoaderCircle } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { streamKnowledgeGraphAnswer } from "@/services/knowledgeGraphApi";
import GraphEvidenceText from "./graphEvidenceText";
import ManualSourceTable from "./manualSourceTable";
import type { Explanation, ManualSource } from "@/services/explanationApi";
import AnswerCallout from "../answer/answerCallout";
import remarkAnswerFormatting from "../answer/remarkAnswerFormatting";
import remarkAnswerCallouts from "../answer/remarkAnswerCallouts";
import answerStyles from "../answer/answer.module.css";
import styles from "./knowledgeGraphPanel.module.css";

export default function KnowledgeGraphAnswer({ messageId, snapshot, originalAnswer, onSelectSource, onClose }: {
  snapshot?: string; originalAnswer: string; onSelectSource: (source: ManualSource) => void;
  messageId: number; onClose: () => void;
}) {
  const [result, setResult] = useState<Explanation>({ answer: "", sources: [] });
  const [selected, setSelected] = useState<number | null>(null);
  function selectSource(source: ManualSource) {
    setSelected(source.index);
    onSelectSource(source);
  }
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const ask = useCallback(async () => {
    if (controller.current) return;
    const request = new AbortController();
    controller.current = request;
    setSelected(null);
    setBusy(true);
    setError(null);
    setResult({ answer: "", sources: [] });
    try {
      const answer = await streamKnowledgeGraphAnswer(messageId, request.signal, partial => {
        if (!request.signal.aborted) setResult(partial);
      }, snapshot);
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
  }, [messageId, snapshot]);

  useEffect(() => {
    void ask();
    return () => {
      controller.current?.abort();
      controller.current = null;
    };
  }, [ask]);

  const cited = new Set(Array.from(result.answer.matchAll(/\[근거\s+(\d+)\]/g), match => Number(match[1])));
  const citedSources = result.sources.filter(source => cited.has(source.index));
  const otherSources = result.sources.filter(source => !cited.has(source.index));
  return <section className={styles.answerPanel} aria-label="지식그래프 기반 답변">
    <header className={styles.answerHeader}>
      <h3>지식그래프 기반 답변</h3>
      <button type="button" title="답변 접기" aria-label="지식그래프 답변 접기" onClick={onClose}><ChevronUp size={18} aria-hidden="true" /></button>
    </header>
    <div className={styles.answerBody}>
      {snapshot && <details className={styles.comparison}><summary>같은 질문의 기존 답변</summary>
        <div className={answerStyles.markdownContent}>
          <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }], remarkAnswerFormatting, remarkAnswerCallouts]}
            components={{
              section: ({ node, children }) => <AnswerCallout title={String(node?.properties["data-callout-title"] ?? "")}
                kind={node?.properties["data-callout-kind"] === "action" ? "action" : "summary"} isGenerating={false}>{children}</AnswerCallout>,
              a: ({ href, children }) => href?.startsWith("#chunk-")
                ? <span className={answerStyles.citationLink}>참조 {children}</span> : <a href={href}>{children}</a>,
            }}>{originalAnswer}</ReactMarkdown>
        </div>
      </details>}
      {busy && <div className={styles.answerLoading} role="status">
        <LoaderCircle size={18} className={styles.spinner} aria-hidden="true" />
        <span>{result.answer ? "답변을 작성하고 있어요…" : "검색 근거로 답변을 만들고 있어요…"}</span>
      </div>}
      <div className={styles.answerText} aria-busy={busy}>
        {snapshot || result.answer.startsWith("> [!") ? <GraphEvidenceText answer={result.answer} sources={result.sources}
          selected={selected} onSelect={selectSource} busy={busy} /> :
          <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]}>{result.answer}</ReactMarkdown>}
      </div>
      {error && <div className={styles.answerError} role="alert">
        <p>{error}</p><button type="button" onClick={() => void ask()}>다시 시도</button>
      </div>}
      {result.sources.length > 0 && <details className={styles.answerSources}>
        <summary>검색 근거 {result.sources.length}개 · 답변에서 인용한 근거 {citedSources.length}개</summary>
        {[...citedSources, ...otherSources].map(source => <details key={source.index}>
          <summary className={cited.has(source.index) ? styles.cited : undefined}
            aria-description={cited.has(source.index) ? "답변에서 인용한 근거" : undefined}
            onClick={() => { if (source.node_id) selectSource(source); }}>[근거 {source.index}] {source.document_name}{source.page ? ` · p.${source.page}` : ""}</summary>
          {source.rows?.length ? <ManualSourceTable rows={source.rows} label={`근거 ${source.index} 원문 표`} /> : <p>{source.excerpt}</p>}
        </details>)}
      </details>}
    </div>
  </section>;
}
