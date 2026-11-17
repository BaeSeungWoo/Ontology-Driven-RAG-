import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { GraphNode, GraphEdge } from "@/services/knowledgeGraphApi";
import { graphLayout, type Point } from "./graphLayout";
import styles from "./manualGraph.module.css";

export const kindLabel = { query: "질문", entity: "개체", passage: "본문 발췌", table: "표 발췌" };
const origin = { x: 0, y: 0 };
const colors = { query: "#1b55cf", both: "#c27724", dense: "#247bbd", ppr: "#2e9271", fact: "#a34796", nearby: "#60728f" };

function NodeMark({ node }: { node: GraphNode }) {
  const role = node.kind === "query" ? "query" : node.dense && node.ppr ? "both" : node.dense ? "dense" : node.ppr ? "ppr" : node.fact ? "fact" : "nearby";
  const fill = role === "query" ? colors.query : `color-mix(in srgb, ${colors[role]} 28%, white)`;
  const ranks = [node.dense_rank && `D${node.dense_rank}`, node.ppr_rank && `G${node.ppr_rank}`].filter(Boolean).join("/");
  return <>
    <title>{node.label}</title>
    {node.kind === "table" ? <path d="M0 -20 L27 0 L0 20 L-27 0 Z" fill={fill} />
      : node.kind === "entity" ? <circle r={node.fact ? 14 : 9} fill={fill} />
      : <rect x={-30} y={-15} width={60} height={30} rx={node.kind === "query" ? 15 : 4} fill={fill} />}
    {node.kind !== "entity" && <text textAnchor="middle" y={4} stroke="none" fill={role === "query" ? "white" : "currentColor"}>{role === "query" ? "질문" : ranks || "주변"}</text>}
    {(node.kind !== "entity" || node.fact) && <foreignObject x={-64} y={21} width={128} height={32} stroke="none">
      <div className={styles.caption} title={node.label}>{node.label}</div>
    </foreignObject>}
  </>;
}

type Camera = { zoom: number; pan: Point };
function zoomAt(camera: Camera, point: Point, factor: number, max: number): Camera {
  const zoom = Math.max(1, Math.min(max, camera.zoom * factor));
  const scale = zoom / camera.zoom;
  return { zoom, pan: { x: point.x - (point.x - camera.pan.x) * scale, y: point.y - (point.y - camera.pan.y) * scale } };
}

export default function GraphCanvas({ nodes, edges, selected, onSelect, view, counts }: {
  nodes: GraphNode[]; edges: GraphEdge[]; selected: string; view: string; counts: string;
  onSelect: (id: string) => void;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const arrow = useId();
  const [size, setSize] = useState({ width: 740, height: 320 });
  const [{ zoom, pan }, setCamera] = useState<Camera>({ zoom: 1, pan: origin });
  const [dragged, setDragged] = useState<Record<string, Point>>({});
  const drag = useRef<{ start: Point; id?: string; initial: Point; moved: boolean } | null>(null);
  const { width, height } = size;
  const { positions, fit } = useMemo(() => graphLayout(nodes, edges, width, height), [nodes, edges, width, height]);
  const point = (id: string) => dragged[id] ?? positions.get(id)!;
  useEffect(() => {
    const element = svg.current!;
    const observer = new ResizeObserver(() => {
      const { width, height } = element.getBoundingClientRect();
      if (width && height) setSize({ width, height });
    });
    observer.observe(element);
    function wheel(event: WheelEvent) {
      event.preventDefault();
      if (!event.deltaY) return;
      const box = element.getBoundingClientRect();
      const at = { x: event.clientX - box.left - box.width / 2, y: event.clientY - box.top - box.height / 2 };
      setCamera(camera => zoomAt(camera, at, event.deltaY < 0 ? 1.12 : 1 / 1.12, 3 / fit));
    }
    element.addEventListener("wheel", wheel, { passive: false });
    return () => { observer.disconnect(); element.removeEventListener("wheel", wheel); };
  }, [fit]);
  const neighbors = new Set([selected]);
  for (const e of edges) {
    if (e.source === selected) neighbors.add(e.target);
    if (e.target === selected) neighbors.add(e.source);
  }
  const nodeSelected = positions.has(selected);
  return <>
    <svg ref={svg} className={styles.canvas} viewBox={`0 0 ${width} ${height}`} role="group" aria-label="매뉴얼 검색 그래프"
      onPointerDown={event => {
        if (event.button !== 0) return;
        const target = event.target as Element;
        if (target.closest("[data-relation]")) return;
        const id = target.closest("[data-node]")?.getAttribute("data-node") ?? undefined;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { start: { x: event.clientX, y: event.clientY }, id, initial: id ? point(id) : pan, moved: false };
      }}
      onPointerMove={event => {
        const active = drag.current;
        if (!active) return;
        const dx = event.clientX - active.start.x, dy = event.clientY - active.start.y;
        if (!active.moved && Math.hypot(dx, dy) < 4) return;
        active.moved = true;
        if (active.id) setDragged(old => ({ ...old, [active.id!]: { x: active.initial.x + dx / (fit * zoom), y: active.initial.y + dy / (fit * zoom) } }));
        else setCamera({ zoom, pan: { x: active.initial.x + dx, y: active.initial.y + dy } });
      }}
      onPointerUp={() => {
        if (drag.current?.id && !drag.current.moved) onSelect(drag.current.id);
        drag.current = null;
      }} onLostPointerCapture={() => { drag.current = null; }}>
      <defs><marker id={arrow} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0 0 L10 5 L0 10 Z" fill="#a34796" /></marker></defs>
      <g transform={`translate(${width / 2 + pan.x} ${height / 2 + pan.y}) scale(${fit * zoom})`}>
        {edges.map(edge => {
          const a = point(edge.source), b = point(edge.target);
          const relation = edge.kind === "relation";
          const distance = Math.hypot(b.x - a.x, b.y - a.y) || 1;
          const offset = relation ? 16 / distance : 0;
          return <g key={edge.id} opacity={nodeSelected && edge.source !== selected && edge.target !== selected ? 0.15 : 1}>
            <line x1={a.x} y1={a.y} x2={b.x - (b.x - a.x) * offset} y2={b.y - (b.y - a.y) * offset}
              stroke={relation ? colors.fact : "#cfd9e8"} strokeDasharray={["direct", "fact_match"].includes(edge.kind) ? "5 5" : undefined}
              strokeWidth={relation ? 2 : 1.2} markerEnd={relation ? `url(#${arrow})` : undefined}
              data-relation={relation || undefined} onClick={relation ? () => onSelect(edge.id) : undefined} />
            {relation && view === "triple" && <text x={(a.x+b.x)/2} y={(a.y+b.y)/2} textAnchor="middle">{edge.label}</text>}
          </g>;
        })}
        {nodes.map(node => {
          const { x, y } = point(node.id);
          return <g key={node.id} data-node={node.id} role="button" tabIndex={0} aria-label={`${kindLabel[node.kind]} ${node.label}`}
            onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(node.id); } }}
            transform={`translate(${x} ${y})`} opacity={nodeSelected && !neighbors.has(node.id) ? 0.24 : 1}
            stroke={node.id === selected ? "currentColor" : "#cfd9e8"} strokeWidth={node.id === selected ? 2 : 1}>
            <NodeMark node={node} />
          </g>;
        })}
      </g>
    </svg>
    <div className={styles.bar}><small>{counts}</small><div className={styles.zoom} role="group" aria-label="그래프 확대 및 축소">
      <button aria-label="축소" disabled={zoom <= 1} onClick={() => setCamera(c => zoomAt(c, origin, 1 / 1.12, 3 / fit))}>−</button>
      <output>{Math.round(100 * zoom)}%</output>
      <button aria-label="확대" disabled={fit * zoom >= 3} onClick={() => setCamera(c => zoomAt(c, origin, 1.12, 3 / fit))}>+</button>
      <button onClick={() => { setCamera({ zoom: 1, pan: origin }); setDragged({}); onSelect(""); }}>초기 화면으로 복원</button>
    </div></div>
  </>;
}
