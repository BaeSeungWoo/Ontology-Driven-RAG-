import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, LoaderCircle, Maximize2, Network, X } from "lucide-react";
import { getKnowledgeGraph, getKnowledgeGraphError, type KnowledgeGraphResult } from "@/services/knowledgeGraphApi";
import KnowledgeGraphAnswer from "./knowledgeGraphAnswer";
import ManualGraph from "./manualGraph";
import styles from "./knowledgeGraphPanel.module.css";

type KnowledgeGraphPanelProps = {
  messageId?: number;
  originalAnswer: string;
  isGenerating: boolean;
};

function GraphViewer({ datasets, question, messageId, snapshot, originalAnswer }: KnowledgeGraphResult & { messageId: number; originalAnswer: string }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [answerRequested, setAnswerRequested] = useState(false);
  const [answerVisible, setAnswerVisible] = useState(false);
  const [manual, setManual] = useState(datasets.find(d => d.nodes.some(n => n.kind !== "query"))?.id);
  const [view, setView] = useState("overall");
  const [node, setNode] = useState("");
  const [graphPercent, setGraphPercent] = useState(55);
  const resizeGraph = (value: number) => setGraphPercent(Math.round(Math.max(30, Math.min(70, value))));
  const dialogRef = useRef<HTMLDialogElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const setExpanded = useCallback((expanded: boolean) => {
    const dialog = dialogRef.current;
    if (!dialog || dialog.matches(":modal") === expanded) return;
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

  return <dialog ref={dialogRef} open className={`${styles.viewer} ${isExpanded ? styles.expanded : ""}`}
    role={isExpanded ? "dialog" : "presentation"} aria-modal={isExpanded || undefined}
    aria-label={isExpanded ? "지식그래프 크게 보기" : undefined}
    onCancel={event => { event.preventDefault(); setExpanded(false); }}>
    <header className={styles.viewerHeader}>
      {isExpanded && <h2><Network size={22} aria-hidden="true" />지식그래프</h2>}
      {isExpanded && answerRequested && !answerVisible && <button type="button" title="답변 펼치기" aria-label="답변 펼치기" onClick={() => setAnswerVisible(true)}>
        <ChevronDown size={18} aria-hidden="true" />
      </button>}
      <button ref={buttonRef} type="button" onClick={() => setExpanded(!isExpanded)}
        title={isExpanded ? "지식그래프 닫기" : "지식그래프 크게 보기"}
        aria-label={isExpanded ? "지식그래프 닫기" : "지식그래프 크게 보기"}
        aria-haspopup={isExpanded ? undefined : "dialog"} aria-expanded={isExpanded}>
        {isExpanded ? <X size={18} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
        {!isExpanded && "크게 보기"}
      </button>
    </header>
    <div style={{ "--graph-width": `${graphPercent}%` } as CSSProperties} className={`${styles.workspace} ${isExpanded && answerVisible ? styles.withAnswer : ""}`}>
      <div className={styles.frame}>
        <ManualGraph datasets={datasets} question={question} manual={manual} view={view} node={node}
          onManual={id => { setManual(id); setNode(""); }} onView={next => { setView(next); setNode(""); }}
          onNode={setNode} onAnswer={() => { setExpanded(true); setAnswerRequested(true); setAnswerVisible(true); }} />
      </div>
      {isExpanded && answerVisible && <div className={styles.divider} role="separator" tabIndex={0}
        aria-label="그래프와 답변 너비 조절" aria-orientation="vertical" aria-valuemin={30} aria-valuemax={70}
        aria-valuenow={graphPercent} aria-valuetext={`그래프 ${graphPercent}%`}
        onPointerDown={event => {
          if (event.button !== 0) return;
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={event => {
          if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
          const bounds = event.currentTarget.parentElement!.getBoundingClientRect();
          resizeGraph(100 * (event.clientX - bounds.left - event.currentTarget.offsetWidth / 2) / bounds.width);
        }}
        onKeyDown={event => {
          if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
          event.preventDefault();
          resizeGraph(graphPercent + (event.key === "ArrowLeft" ? -2 : 2));
        }} />}
      {answerRequested && <div className={styles.answerContainer} hidden={!isExpanded || !answerVisible}>
        <KnowledgeGraphAnswer messageId={messageId} snapshot={snapshot}
          originalAnswer={originalAnswer} onSelectSource={source => {
            const dataset = datasets.find(d => d.id === source.corpus);
            if (!dataset?.nodes.some(n => n.id === source.node_id && n.final)) return;
            setManual(dataset.id);
            setView("overall");
            setNode(source.node_id!);
          }} onClose={() => {
          setAnswerVisible(false);
          buttonRef.current?.focus({ preventScroll: true });
        }} />
      </div>}
    </div>
  </dialog>;
}

export default function KnowledgeGraphPanel({ messageId, isGenerating, originalAnswer }: KnowledgeGraphPanelProps) {
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
      <GraphViewer key={messageId} {...result} messageId={messageId} originalAnswer={originalAnswer} />
    </> : <div className={styles.state} role="status">
      <LoaderCircle className={styles.spinner} size={28} aria-hidden="true" />
      <p>질문과 관련된 매뉴얼과 지식 연결을 찾고 있어요.<br />처음 검색할 때는 시간이 걸릴 수 있습니다.</p>
    </div>}
  </section>;
}
