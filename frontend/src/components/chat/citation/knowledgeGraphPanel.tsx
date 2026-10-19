import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LoaderCircle, Maximize2, Network, X } from "lucide-react";
import { getKnowledgeGraph, getKnowledgeGraphError, type KnowledgeGraphResult } from "@/services/knowledgeGraphApi";
import KnowledgeGraphAnswer from "./knowledgeGraphAnswer";
import styles from "./knowledgeGraphPanel.module.css";

type KnowledgeGraphPanelProps = {
  messageId?: number;
  isGenerating: boolean;
};

function GraphViewer({ html, messageId, question }: { html: string; messageId: number; question: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [answerRequested, setAnswerRequested] = useState(false);
  const [answerVisible, setAnswerVisible] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const frameRef = useRef<HTMLIFrameElement>(null);
  // Keyboard events inside the sandboxed frame do not reach the parent dialog.
  const viewerHtml = useMemo(() => html.replace("</body>", `<script>
    const answerButton = document.createElement("button");
    answerButton.type = "button";
    answerButton.className = "btn";
    answerButton.textContent = "지식그래프 기반으로 답변받기";
    answerButton.style.cssText = "border-color:var(--ring);color:var(--ring);font-weight:600";
    answerButton.addEventListener("click", () => parent.postMessage("knowledge-graph:answer", "*"));
    document.querySelector('[data-view="ppr"]').after(answerButton);
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && !event.defaultPrevented) parent.postMessage("knowledge-graph:escape", "*");
    });
  </script></body>`), [html]);

  const setExpanded = useCallback((expanded: boolean) => {
    const dialog = dialogRef.current;
    if (!dialog || dialog.matches(":modal") === expanded) return;
    // Keep the same iframe mounted so its selected manual and node survive resizing.
    dialog.close();
    if (expanded) dialog.showModal();
    else dialog.show();
    setIsExpanded(expanded);
    buttonRef.current?.focus({ preventScroll: true });
  }, []);

  useEffect(() => {
    if (!isExpanded) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previousOverflow; };
  }, [isExpanded]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.source !== frameRef.current?.contentWindow) return;
      if (event.data === "knowledge-graph:escape" && isExpanded) {
        setExpanded(false);
      } else if (event.data === "knowledge-graph:answer") {
        setExpanded(true);
        setAnswerRequested(true);
        setAnswerVisible(true);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
    };
  }, [isExpanded, setExpanded]);

  return <dialog ref={dialogRef} open className={`${styles.viewer} ${isExpanded ? styles.expanded : ""}`}
    role={isExpanded ? "dialog" : "presentation"} aria-modal={isExpanded || undefined}
    aria-label={isExpanded ? "지식그래프 크게 보기" : undefined}
    onCancel={event => { event.preventDefault(); setExpanded(false); }}>
    <header className={styles.viewerHeader}>
      <h2 hidden={!isExpanded}>지식그래프</h2>
      <button ref={buttonRef} type="button" onClick={() => setExpanded(!isExpanded)}
        aria-label={isExpanded ? "지식그래프 닫기" : "지식그래프 크게 보기"}
        aria-haspopup={isExpanded ? undefined : "dialog"} aria-expanded={isExpanded}>
        {isExpanded ? <X size={18} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
        {isExpanded ? "닫기" : "크게 보기"}
      </button>
    </header>
    <div className={`${styles.workspace} ${isExpanded && answerVisible ? styles.withAnswer : ""}`}>
      <iframe ref={frameRef} className={styles.frame} title="선택한 질문의 매뉴얼 검색 지식그래프"
        srcDoc={viewerHtml} sandbox="allow-scripts" />
      {answerRequested && <div className={styles.answerContainer} hidden={!isExpanded || !answerVisible}>
        <KnowledgeGraphAnswer messageId={messageId} question={question} onClose={() => {
          setAnswerVisible(false);
          buttonRef.current?.focus({ preventScroll: true });
        }} />
      </div>}
    </div>
  </dialog>;
}

export default function KnowledgeGraphPanel({ messageId, isGenerating }: KnowledgeGraphPanelProps) {
  const [result, setResult] = useState<KnowledgeGraphResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!messageId || isGenerating) return;
    const request = new AbortController();
    getKnowledgeGraph(messageId, request.signal).then(data => {
      if (!request.signal.aborted) { setResult(data); setError(null); }
    }).catch(cause => {
      if (!request.signal.aborted) setError(getKnowledgeGraphError(cause));
    });
    return () => request.abort();
  }, [messageId, isGenerating, attempt]);

  return <section className={styles.panel} aria-label="질문 관련 매뉴얼 검색">
    <div className={styles.heading}>
      <h3>질문 관련 매뉴얼 검색</h3>
      <p>선택한 질문으로 매뉴얼을 추가 검색한 결과입니다.</p>
    </div>
    {!messageId ? <div className={styles.state} role="status">
      <Network size={40} strokeWidth={1.6} aria-hidden="true" />
      <p>질문하고 답변을 선택하면 관련 매뉴얼의 지식그래프를 확인할 수 있어요.</p>
    </div> : isGenerating ? <div className={styles.state} role="status">
      <LoaderCircle className={styles.spinner} size={28} aria-hidden="true" />
      <p>답변이 완료되면 질문 관련 매뉴얼 검색을 시작합니다.</p>
    </div> : error ? <div className={styles.state}>
      <p role="alert">{error}</p>
      <button type="button" onClick={() => { setError(null); setResult(null); setAttempt(value => value + 1); }}>
        다시 시도
      </button>
    </div> : result ? <>
      <p className={styles.question}>{result.question}</p>
      <p className={styles.corpora}>검색 매뉴얼: {result.corpora.map(corpus => corpus.toUpperCase()).join(" · ")}</p>
      <GraphViewer html={result.html} messageId={messageId} question={result.question} />
    </> : <div className={styles.state} role="status">
      <LoaderCircle className={styles.spinner} size={28} aria-hidden="true" />
      <p>질문과 관련된 매뉴얼과 지식 연결을 찾고 있어요.<br />처음 검색할 때는 시간이 걸릴 수 있습니다.</p>
    </div>}
  </section>;
}
