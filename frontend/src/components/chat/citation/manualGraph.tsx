import { ChevronDown } from "lucide-react";
import type { GraphDataset, GraphNode } from "@/services/knowledgeGraphApi";
import GraphCanvas, { kindLabel } from "./graphCanvas";
import ManualSourceTable from "./manualSourceTable";
import styles from "./manualGraph.module.css";

const views = { overall: "전체 연결", dense: "질문 → 본문·표", triple: "질문 → 관계", ppr: "그래프 탐색 결과" };
const legend = [
  ["#a34796", "관계 시작 개체"], ["#247bbd", "직접 검색 D"], ["#2e9271", "그래프 탐색 G"], ["#c27724", "두 방식 공통"],
];

function NodeDetail({ node }: { node: GraphNode }) {
  const title = node.caption || node.label;
  const scores = [
    node.dense_rank && `직접 D${node.dense_rank}`, node.ppr_rank && `탐색 G${node.ppr_rank}`,
    node.final && "현재 인덱스 최종 후보", node.cosine != null && `질문 유사도 ${node.cosine.toFixed(3)}`,
    node.ppr_score != null && `탐색 점수 ${node.ppr_score.toExponential(2)}`,
  ].filter(Boolean);
  let rows = node.rows;
  if (node.kind === "table" && !rows) {
    const lines = node.content.trim().split(/\r?\n/);
    if (lines[0] === title) lines.shift();
    rows = lines.map(line => line.trim().replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map(text => ({ text: text.trim().replace(/\\\|/g, "|") })));
    if (rows[1]?.every(cell => /^:?-{3,}:?$/.test(cell.text))) rows.splice(1, 1);
  }
  return <article className={styles.detail} aria-live="polite">
    <small>{kindLabel[node.kind]}</small><h4>{title}</h4>
    {node.document && <small>{node.document} · p.{node.pages}</small>}
    <small>{scores.join(" · ")}</small>
    {rows?.length ? <ManualSourceTable rows={rows.map(row => row.map(cell => ({ ...cell, text: cell.text.replace(/\\n/g, "\n") })))} label={title} />
      : <p>{node.content}</p>}
  </article>;
}

export default function ManualGraph({ expanded, datasets, question, manual, view, node, onManual, onView, onNode, onAnswer }: {
  expanded: boolean; datasets: GraphDataset[]; question: string; manual?: string; view: string; node: string;
  onManual: (id: string) => void; onView: (view: string) => void; onNode: (id: string) => void; onAnswer: () => void;
}) {
  const linked = datasets.filter(d => d.nodes.some(n => n.kind !== "query"));
  const unlinked = datasets.filter(d => !linked.includes(d));
  const data = linked.find(d => d.id === manual) ?? linked[0];
  const active = data?.views[view] ? view : "overall";
  const membership = data?.views[active];
  const nodes = data?.nodes.filter(n => membership?.nodes.includes(n.id)) ?? [];
  const edges = data?.edges.filter(e => membership?.edges.includes(e.id)) ?? [];
  const selected = nodes.find(n => n.id === node);
  const relation = edges.find(e => e.kind === "relation" && e.id === node);
  const counts = data?.index_counts;
  if (!expanded) return data
    ? <GraphCanvas nodes={nodes} edges={edges} view={active} selected="" />
    : <p className={styles.board} role="status">이 질문에 연결된 근거가 있는 매뉴얼이 없습니다.</p>;
  return <section className={styles.board} aria-label="질문에서 근거까지">
    <div className={styles.controls}>
    <div className={styles.bar}><h3>질문에서 근거까지</h3>{data && <small>{data.id.toUpperCase()} · 표본 부분 그래프</small>}</div>
    <div className={styles.question}><strong>질문</strong>{question}</div>
    <label className={styles.field}>매뉴얼<select value={data?.id ?? ""} disabled={!data} onChange={e => onManual(e.target.value)}>
      {!data && <option value="">연결 근거 없음</option>}
      {linked.map(d => <option key={d.id} value={d.id}>{d.title}</option>)}
    </select><ChevronDown size={15} aria-hidden="true" /></label>
    {!!unlinked.length && <details className={styles.unlinked}><summary>연결 근거 없는 매뉴얼 {unlinked.length}개</summary>
      <ul>{unlinked.map(d => <li key={d.id}>{d.title}</li>)}</ul></details>}
    {data && counts ? <>
      <div className={styles.actions} role="group" aria-label="탐색 단계">
        {Object.entries(views).filter(([key]) => data.views[key]).map(([key, label]) =>
          <button key={key} aria-pressed={active === key} onClick={() => onView(key)}>{label}</button>)}
        <button onClick={onAnswer}>지식그래프 기반으로 답변받기</button>
      </div>
      <div className={styles.legend} aria-label="색과 모양 범례">{legend.map(([color, label]) =>
        <span key={label}><i style={{ background: color }} />{label}</span>)}<span>○ 개체</span><span>▭ 본문</span><span>◇ 표</span></div>
      <GraphCanvas key={data.id + "/" + active} nodes={nodes} edges={edges} view={active} selected={node} onSelect={onNode}
        counts={`표시 ${nodes.length}노드 · ${edges.length}연결 / 전체 개체 ${counts.entities.toLocaleString()} · 본문 ${counts.passages.toLocaleString()} · 표 ${counts.tables.toLocaleString()}`} />
      <small>실선: 저장된 연결 · 점선: 질문 유사도 · 단계별 상위 결과와 주변 연결</small>
      <label className={styles.field}>노드 원문<select value={selected?.id ?? ""} onChange={e => onNode(e.target.value)}>
        <option value="">노드 선택</option>{nodes.map(n => <option key={n.id} value={n.id}>{kindLabel[n.kind]} · {n.caption || n.label}</option>)}
      </select><ChevronDown size={15} aria-hidden="true" /></label>
    </> : <p role="status">이 질문에 연결된 근거가 있는 매뉴얼이 없습니다.</p>}
    </div>
    {selected && <NodeDetail node={selected} />}
      {relation && <article className={styles.detail} aria-live="polite"><small>추출 관계 · 원문 검토 대상</small><h4>{relation.label}</h4>
        <small>{relation.sources?.map(s => `${s.document} · p.${s.pages}`).join(" / ")}</small>
        {relation.cosine != null && <small>질문–관계 유사도 {relation.cosine.toFixed(3)}</small>}
        <p>{nodes.find(n => n.id === relation.source)?.label} → {relation.label} → {nodes.find(n => n.id === relation.target)?.label}</p>
      </article>}
  </section>;
}
