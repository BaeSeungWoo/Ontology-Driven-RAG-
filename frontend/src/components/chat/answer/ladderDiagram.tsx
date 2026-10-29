import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import useLadderSignals from "@/hooks/useLadderSignals";
import { getLadderSignals, getTestLadder, type MachineLadderDocument } from "@/services/ladderApi";
import { useMachine } from "@/components/machineProvider";
import type { ChatChunk } from "@/types/chatApi";
import type { LadderContact, LadderDiagram, LadderNode } from "@/types/ladder";
import styles from "./ladderDiagram.module.css";
import { getMessageReferenceItems, getReferenceLabelMap } from "../citation/citationUtils";

type Layout = { node: LadderNode; width: number; height: number; children: Layout[] };

function measure(node: LadderNode): Layout {
  if (node.kind === "contact") return { node, width: 160, height: 112, children: [] };
  if (node.kind === "function") {
    const input = measure(node.input);
    return { node, width: input.width + 200, height: input.height, children: [input] };
  }
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

function wire(x1: number, y1: number, x2: number, y2: number, powered = false) {
  return <line x1={x1} y1={y1} x2={x2} y2={y2} className={`${styles.wire}${powered ? ` ${styles.poweredWire}` : ""}`} />;
}

type SignalValues = Map<string, 0 | 1 | null>;
const normalizeAddress = (address: string) => address.replace(/^([A-Z])0+(\d)/, "$1$2");

function conducts(node: LadderNode, values: SignalValues): boolean {
  if (node.kind === "contact") return values.get(normalizeAddress(node.addr)) === (node.neg ? 0 : 1);
  // SUB의 출력 논리는 해석하지 않는다. 입력 상태만으로 뒤쪽 배선을 켜지 않는다.
  if (node.kind === "function") return false;
  return node.kind === "series"
    ? node.children.every(child => conducts(child, values))
    : node.children.some(child => conducts(child, values));
}

function symbol(node: LadderContact, x: number, y: number, values: SignalValues, coil = false) {
  const value = values.get(normalizeAddress(node.addr));
  const on = value === 0 || value === 1 ? (coil ? value === 1 : value === (node.neg ? 0 : 1)) : false;
  return (
    <g className={on ? styles.energized : undefined}>
      <title>{`${node.addr} · ${node.label} · ${node.description}${node.neg ? " · 반전" : ""} · ${value === 0 || value === 1 ? `수신값 ${value}` : "신호 미확인"}`}</title>
      {!coil && on && <rect x={x - 24} y={y - 23} width={48} height={46} rx={7} className={styles.signalBackground} />}
      <text x={x} y={y - 27} className={styles.address}>{node.addr}</text>
      {coil ? (
        <circle cx={x} cy={y} r={20} className={`${styles.wire} ${styles.coil}`} />
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

function draw(layout: Layout, x: number, y: number, values: SignalValues, powerIn: boolean): ReactNode {
  if (layout.node.kind === "function") {
    const input = layout.children[0];
    const left = x + input.width;
    const label = `SUB ${layout.node.code}${layout.node.name ? ` · ${layout.node.name}` : ""}`;
    const argumentsText = layout.node.arguments.join(", ") || "없음";
    return <>
      {draw(input, x, y, values, powerIn)}
      {wire(left, y, left + 20, y, powerIn && conducts(input.node, values))}
      <g>
        <title>{`${label} · 원문 인수: ${argumentsText} · 내부 동작 미해석`}</title>
        <rect x={left + 20} y={y - 24} width={160} height={52} className={styles.wire} />
        <text x={left + 100} y={y - 5} className={styles.address}>{label.length > 20 ? `${label.slice(0, 19)}…` : label}</text>
        <text x={left + 100} y={y + 16} className={styles.label}>인수: {argumentsText.length > 22 ? `${argumentsText.slice(0, 21)}…` : argumentsText}</text>
        <text x={left + 100} y={y + 48} className={styles.label}>기능 블록 · 내부 동작 미해석</text>
      </g>
      {wire(left + 180, y, left + 200, y)}
    </>;
  }
  if (layout.node.kind === "contact") {
    return <>{wire(x, y, x + 64, y, powerIn)}{symbol(layout.node, x + 80, y, values)}{wire(x + 96, y, x + 160, y, powerIn && conducts(layout.node, values))}</>;
  }
  let offset = 0;
  if (layout.node.kind === "series") {
    let powered = powerIn;
    return layout.children.map((child, index) => {
      const left = x + offset;
      offset += child.width;
      const inputPower = powered;
      powered = powered && conducts(child.node, values);
      return <Fragment key={index}>{draw(child, left, y, values, inputPower)}</Fragment>;
    });
  }
  const lastY = y + layout.height - layout.children[layout.children.length - 1].height;
  const branchPower = layout.children.map(child => powerIn && conducts(child.node, values));
  return (
    <>
      {wire(x, y, x + 12, y, powerIn)}
      {wire(x + 12, y, x + 12, lastY, powerIn)}
      {wire(x + layout.width - 12, y, x + layout.width, y, branchPower.some(Boolean))}
      {layout.children.map((child, index) => {
        const top = y + offset;
        offset += child.height;
        return (
          <Fragment key={index}>
            {wire(x + 12, top, x + 24, top, powerIn)}
            {draw(child, x + 24, top, values, powerIn)}
            {wire(x + 24 + child.width, top, x + layout.width - 12, top, branchPower[index])}
            {index < layout.children.length - 1 && wire(x + layout.width - 12, top,
              x + layout.width - 12, top + child.height, branchPower.slice(index + 1).some(Boolean))}
          </Fragment>
        );
      })}
    </>
  );
}

function descriptionLines(text: string): string[] {
  return text.match(/.{1,32}(?:\s|$)|.{1,32}/g)?.map(line => line.trim()) || [];
}

function LadderCircuit({ diagram, values, symbols }: {
  diagram: LadderDiagram; values: SignalValues; symbols?: MachineLadderDocument["symbols"];
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const [availableWidth, setAvailableWidth] = useState(0);
  useEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setAvailableWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  if (diagram.status !== "supported") return <p className={styles.note}>이 근거는 회로 미리보기를 지원하지 않습니다.</p>;
  const layout = measure(diagram.logic);
  const coils = diagram.coils ?? [diagram.coil];
  const powerIn = [...values.values()].some(value => value === 0 || value === 1);
  const powerOut = powerIn && conducts(diagram.logic, values);
  const descriptions = coils.map(coil => {
    const entry = symbols?.[normalizeAddress(coil.addr)];
    return descriptionLines(coil.description.trim() || entry?.comment?.trim() || entry?.short?.trim() || "");
  });
  const commentWidth = descriptions.some(lines => lines.length) ? 250 : 0;
  const width = Math.max(availableWidth, layout.width + 240 + commentWidth);
  const rightRail = width - commentWidth - 20;
  const rowHeight = Math.max(112, ...descriptions.map(lines => lines.length * 16 + 32));
  const height = Math.max(layout.height, coils.length * rowHeight) + 16;
  return (
    <div ref={viewport} className={styles.viewport} tabIndex={0} role="region" aria-label={`${diagram.nblock} 래더 도면 가로 스크롤`}>
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${diagram.nblock} 래더 회로, 출력 ${coils.map(coil => coil.addr).join(", ")}`}>
      <title>{`${diagram.nblock} 접점·기능 블록·출력의 명령 흐름`}</title>
      {wire(20, 16, 20, height - 16)}
      {wire(rightRail, 16, rightRail, height - 16)}
      {wire(20, 48, 40, 48, powerIn)}
      {draw(layout, 40, 48, values, powerIn)}
      {wire(40 + layout.width, 48, rightRail - 120, 48, powerOut)}
      {coils.length > 1 && wire(rightRail - 120, 48, rightRail - 120, 48 + (coils.length - 1) * rowHeight, powerOut)}
      {coils.map((coil, index) => {
        const y = 48 + index * rowHeight;
        return <Fragment key={index}>
          {wire(rightRail - 120, y, rightRail - 100, y, powerOut)}
          {symbol(coil, rightRail - 80, y, values, true)}
          {wire(rightRail - 60, y, rightRail, y, values.get(normalizeAddress(coil.addr)) === 1)}
          <text x={rightRail + 12} y={y + 4} className={styles.description}>
            {descriptions[index].map((line, lineIndex) => <tspan key={lineIndex} x={rightRail + 12} dy={lineIndex ? 16 : 0}>{line}</tspan>)}
          </text>
        </Fragment>;
      })}
    </svg>
    </div>
  );
}

export default function LadderDiagrams({ chunks, answerText, onSource }: {
  chunks: ChatChunk[];
  answerText: string;
  onSource: (index: number) => void;
}) {
  const { executionMachineCode: machineCode } = useMachine();
  const root = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);
  const [opened, setOpened] = useState<Record<string, boolean>>({});
  const [ladderDocument, setLadderDocument] = useState<MachineLadderDocument | null>(null);
  const diagrams = useMemo(() => {
    const seen = new Set<string>();
    const cited = getReferenceLabelMap(answerText);
    return chunks.filter((chunk) => {
      const diagram = chunk.metadata.ladder_diagram;
      if (!cited.has(chunk.index) || !diagram || seen.has(diagram.nblock)) return false;
      seen.add(diagram.nblock);
      return true;
    });
  }, [chunks, answerText]);
  useEffect(() => {
    if (!root.current) return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting));
    observer.observe(root.current);
    return () => observer.disconnect();
  }, [diagrams.length]);
  useEffect(() => {
    setLadderDocument(null);
    if (!visible || !machineCode || machineCode === "ALL") return;
    const controller = new AbortController();
    void getTestLadder(controller.signal, machineCode).then(document => {
      if (!controller.signal.aborted) setLadderDocument(document);
    }).catch(() => {});
    return () => controller.abort();
  }, [visible, machineCode]);
  const matchesMachine = (chunk: ChatChunk) => {
    const codes = chunk.metadata.machine_code;
    return !!machineCode && (Array.isArray(codes)
      ? codes.some(code => String(code).trim() === machineCode)
      : typeof codes === "string" && codes.split(/[^A-Za-z0-9_-]+/).includes(machineCode));
  };
  const addressKey = [...new Set(diagrams.filter((chunk) =>
    (opened[chunk.metadata.ladder_diagram!.nblock] ?? false) && matchesMachine(chunk)
  ).flatMap(chunk => getLadderSignals(chunk.metadata.ladder_diagram).map(signal => signal.address)))].sort().join(",");
  const addresses = useMemo(() => addressKey ? addressKey.split(",") : [], [addressKey]);
  const { snapshot, error } = useLadderSignals(addresses, !visible);
  const values: SignalValues = new Map(visible && !error && snapshot && snapshot.machine.code === machineCode
    ? snapshot.signals.filter(signal => addresses.includes(signal.address)).map(signal => [signal.address, signal.value]) : []);
  if (!diagrams.length) return null;
  const references = getMessageReferenceItems({ content: answerText, llm_mode: "ladder", metadata: { chunks } });

  return (
    <section ref={root} className={styles.root} aria-label="검색된 래더 도면">
      <p className={styles.heading}>검색된 래더 근거</p>
      {diagrams.map((chunk) => {
        const diagram = chunk.metadata.ladder_diagram!;
        const reference = references.find((item) => item.chunkIndex === chunk.index)!;
        const layout = diagram.status === "supported" ? measure(diagram.logic) : null;
        return (
          <details key={diagram.nblock} className={styles.card} open={opened[diagram.nblock] ?? false}
            onToggle={event => {
              if (event.target !== event.currentTarget) return;
              const open = event.currentTarget.open;
              setOpened(previous => previous[diagram.nblock] === open ? previous : { ...previous, [diagram.nblock]: open });
            }}>
            <summary>{diagram.nblock} · {diagram.status === "supported" ? (diagram.coils ?? [diagram.coil]).map(coil => `${coil.addr} ${coil.label}`).join(", ") : "원본 명령"}</summary>
            <div className={styles.body}>
              <p className={styles.note}>답변에서 인용한 근거 · 참조 [{reference.label}]</p>
              {layout && diagram.status === "supported" ? (
                <>
                  <p className={styles.note}>배선 색상은 수신값과 접점 논리로 계산합니다. SUB는 내부 동작을 해석하지 않아 입력만으로 뒤쪽 배선을 켜지 않습니다.</p>
                  <p className={styles.note} role="status">{!matchesMachine(chunk) ? "연결 장비와 근거의 장비 일치를 확인할 수 없어 실시간 신호를 표시하지 않습니다."
                    : error || (snapshot && snapshot.machine.code === machineCode
                      ? `${snapshot.machine.name} · ${snapshot.machine.code} · ${new Date(snapshot.read_completed).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul" })} 수신 · 녹색: a접점 1 / b접점 0 / 코일 1 · 미수신 주소는 색칠하지 않습니다.`
                      : "장비 신호 연결 대기 중")}</p>
                  <LadderCircuit diagram={diagram} values={matchesMachine(chunk) ? values : new Map()}
                    symbols={matchesMachine(chunk) && ladderDocument && ladderDocument.meta.machine_code === machineCode ? ladderDocument.symbols : undefined} />
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
