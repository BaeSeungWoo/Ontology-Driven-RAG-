import type { GraphNode, GraphEdge } from "@/services/knowledgeGraphApi";

export type Point = { x: number; y: number };

export function graphLayout(nodes: GraphNode[], edges: GraphEdge[], width: number, height: number) {
  const positions = new Map<string, Point>();
  const center = nodes.find(node => node.kind === "query") ?? nodes[0];
  if (!center) return { positions, fit: 1 };
  const neighbors = new Map(nodes.map(node => [node.id, [] as string[]]));
  for (const edge of edges) {
    neighbors.get(edge.source)?.push(edge.target);
    neighbors.get(edge.target)?.push(edge.source);
  }
  const parents = new Map<string, string>([[center.id, center.id]]);
  const rings = [[center.id]];
  for (const ring of rings) {
    const next: string[] = [];
    for (const id of ring) {
      for (const neighbor of neighbors.get(id) ?? []) {
        if (parents.has(neighbor)) continue;
        parents.set(neighbor, id);
        next.push(neighbor);
      }
    }
    if (next.length) rings.push(next);
  }
  const disconnected = nodes.filter(n => !parents.has(n.id)).map(n => n.id);
  if (disconnected.length) rings.push(disconnected);
  positions.set(center.id, { x: 0, y: 0 });
  const angles = new Map<string, number>();
  const ry = Math.max(70, height / 2 - 48);
  const rx = Math.max(80, width / 2 - 72);
  rings.slice(1).forEach((ring, index) => {
    const step = 2 * Math.PI / ring.length;
    let dx = 0, dy = 0;
    ring.forEach((id, i) => {
      const angle = angles.get(parents.get(id) ?? "");
      if (angle === undefined) return;
      dx += Math.cos(angle - i * step);
      dy += Math.sin(angle - i * step);
    });
    const start = Math.hypot(dx, dy) > 0.001 ? Math.atan2(dy, dx) : -Math.PI / 2;
    const fraction = (index + 1) / (rings.length - 1);
    ring.forEach((id, i) => {
      const angle = start + i * step;
      angles.set(id, angle);
      positions.set(id, { x: Math.cos(angle) * rx * fraction, y: Math.sin(angle) * ry * fraction });
    });
  });

  // Reserve space for the mark and its two-line caption while keeping the question centered.
  const boxes = nodes.map(n => ({
    point: positions.get(n.id)!, fixed: n === center,
    width: n.kind === "entity" && !n.fact ? 20 : Math.min(128, Math.max(60, Array.from(n.label).length * 12)),
    height: n.kind === "entity" && !n.fact ? 20 : 72,
  }));
  for (let pass = 0; pass < 160; pass++) {
    let moved = false;
    boxes.forEach((a, i) => {
      for (const b of boxes.slice(i + 1)) {
        const dx = b.point.x - a.point.x, dy = b.point.y - a.point.y;
        const ox = (a.width + b.width) / 2 + 12 - Math.abs(dx);
        const oy = (a.height + b.height) / 2 + 8 - Math.abs(dy);
        if (ox <= 0 || oy <= 0) continue;
        const axis = ox < oy ? "x" : "y";
        const shift = Math.sign((ox < oy ? dx : dy) || 1) * (Math.min(ox, oy) + 0.4);
        if (!a.fixed) a.point[axis] -= b.fixed ? shift : shift / 2;
        if (!b.fixed) b.point[axis] += a.fixed ? shift : shift / 2;
        moved = true;
      }
    });
    if (!moved) break;
  }
  const maxX = Math.max(...boxes.map(b => Math.abs(b.point.x) + b.width / 2));
  const maxY = Math.max(...boxes.map(b => Math.max(20 - b.point.y, b.point.y + 56)));
  return { positions, fit: Math.min(1, (width / 2 - 8) / maxX, (height / 2 - 8) / maxY) };
}
