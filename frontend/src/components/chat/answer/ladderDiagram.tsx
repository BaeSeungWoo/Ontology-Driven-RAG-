import { Fragment, type ReactNode } from "react";
import type { ChatChunk } from "@/types/chatApi";
import type { LadderContact, LadderNode } from "@/types/ladder";
import styles from "./ladderDiagram.module.css";
import { getMessageReferenceItems } from "../citation/citationUtils";

type Layout = { node: LadderNode; width: number; height: number; children: Layout[] };

function measure(node: LadderNode): Layout {
  if (node.kind === "contact") return { node, width: 160, height: 112, children: [] };
  const children = node.children.map(measure);
  return {
    node, children,
    width: node.kind === "series"
      ? children.reduce((sum, child) => sum + child.width, 0)
      : Math.max(...children.map((child) => child.width)) + 48,
    height: node.kind === "series"
      ? Math.max(...children.map((child) => child.height))
      : children.reduce((sum, child) => sum + child.height, 0),
  };
}

function wire(x1: number, y1: number, x2: number, y2: number) {
  return <line x1={x1} y1={y1} x2={x2} y2={y2} className={styles.wire} />;
}

function symbol(node: LadderContact, x: number, y: number, coil = false) {
  return (
    <g>
      <title>{`${node.addr} · ${node.label} · ${node.description}${node.neg ? " · 반전" : ""}`}</title>
      <text x={x} y={y - 27} className={styles.address}>{node.addr}</text>
      {coil ? (
        <path d={`M ${x - 12} ${y - 16} Q ${x - 28} ${y} ${x - 12} ${y + 16} M ${x + 12} ${y - 16} Q ${x + 28} ${y} ${x + 12} ${y + 16}`} className={styles.wire} />
      ) : (
        <>{wire(x - 16, y - 17, x - 16, y + 17)}{wire(x + 16, y - 17, x + 16, y + 17)}</>
      )}
      {node.neg && wire(x - 21, y + 19, x + 21, y - 19)}
      <text x={x} y={y + 39} className={styles.label}>
        {node.label.length > 19 ? `${node.label.slice(0, 18)}…` : node.label}
      </text>
    </g>
  );
}

function draw(layout: Layout, x: number, y: number): ReactNode {
  if (layout.node.kind === "contact") {
    return <>{wire(x, y, x + 64, y)}{symbol(layout.node, x + 80, y)}{wire(x + 96, y, x + 160, y)}</>;
  }
  let offset = 0;
  if (layout.node.kind === "series") {
    return layout.children.map((child, index) => {
      const left = x + offset;
      offset += child.width;
      return <Fragment key={index}>{draw(child, left, y)}</Fragment>;
    });
  }
  const lastY = y + layout.height - layout.children[layout.children.length - 1].height;
  return (
    <>
      {wire(x, y, x + 12, y)}
      {wire(x + 12, y, x + 12, lastY)}
      {wire(x + layout.width - 12, y, x + layout.width - 12, lastY)}
      {wire(x + layout.width - 12, y, x + layout.width, y)}
      {layout.children.map((child, index) => {
        const top = y + offset;
        offset += child.height;
        return (
          <Fragment key={index}>
            {wire(x + 12, top, x + 24, top)}
            {draw(child, x + 24, top)}
            {wire(x + 24 + child.width, top, x + layout.width - 12, top)}
          </Fragment>
        );
      })}
    </>
  );
}

export default function LadderDiagrams({ chunks, answerText, onSource }: {
  chunks: ChatChunk[];
  answerText: string;
  onSource: (index: number) => void;
}) {
  const seen = new Set<string>();
  const diagrams = chunks.filter((chunk) => {
    const diagram = chunk.metadata.ladder_diagram;
    if (!diagram || seen.has(diagram.nblock)) return false;
    seen.add(diagram.nblock);
    return true;
  });
  if (!diagrams.length) return null;
  const references = getMessageReferenceItems({ content: answerText, llm_mode: "ladder", metadata: { chunks } });

  return (
    <section className={styles.root} aria-label="검색된 래더 도면">
      <p className={styles.heading}>검색된 래더 근거</p>
      {diagrams.map((chunk, index) => {
        const diagram = chunk.metadata.ladder_diagram!;
        const reference = references.find((item) => item.chunkIndex === chunk.index)!;
        const layout = diagram.status === "supported" ? measure(diagram.logic) : null;
        const width = layout ? layout.width + 240 : 0;
        const height = layout ? layout.height + 16 : 0;
        return (
          <details key={diagram.nblock} className={styles.card} open={index === 0}>
            <summary>{diagram.nblock} · {diagram.status === "supported" ? `${diagram.coil.addr} ${diagram.coil.label}` : "원본 명령"}</summary>
            <div className={styles.body}>
              <p className={styles.note}>{reference.additional ? "추가 검색된 근거" : "답변에서 인용한 근거"} · 참조 [{reference.label}]</p>
              {layout && diagram.status === "supported" ? (
                <>
                  <p className={styles.note}>명령 기반 재구성 · 통전 색상 없음 · 가로 스크롤로 전체 회로를 확인하세요.</p>
                  <div className={styles.viewport} tabIndex={0} role="region" aria-label={`${diagram.nblock} 래더 도면 가로 스크롤`}>
                    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${diagram.nblock} 래더 회로, 출력 ${diagram.coil.addr}`}>
                      <title>{diagram.nblock} 접점과 코일의 논리 연결</title>
                      {wire(20, 16, 20, height - 16)}
                      {wire(width - 20, 16, width - 20, height - 16)}
                      {wire(20, 48, 40, 48)}
                      {draw(layout, 40, 48)}
                      {wire(40 + layout.width, 48, width - 120, 48)}
                      {symbol(diagram.coil, width - 100, 48, true)}
                      {wire(width - 80, 48, width - 20, 48)}
                    </svg>
                  </div>
                </>
              ) : <p className={styles.note}>특수 명령 또는 지원하지 않는 구조가 포함되어 원본 명령을 표시합니다.</p>}
              <details className={styles.instructions} open={diagram.status === "unsupported"}>
                <summary>원본 명령 보기</summary>
                <pre>{diagram.instructions.join("\n")}</pre>
              </details>
              <button type="button" className={styles.source} onClick={() => onSource(chunk.index)}>참조 [{reference.label}] 보기</button>
            </div>
          </details>
        );
      })}
    </section>
  );
}
