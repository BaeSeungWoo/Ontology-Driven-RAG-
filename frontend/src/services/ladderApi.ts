import api from "./api";
import type { LadderDiagram, LadderNode } from "@/types/ladder";

export type PmcSnapshot = {
  test_mode: true;
  machine: { code: string; name: string; ip: string };
  read_completed: string;
  signals: { address: string; value: 0 | 1 | null; error: string | null }[];
};

export function getLadderSignals(diagram?: LadderDiagram) {
  const signals = new Map<string, { address: string; label: string; description: string }>();
  const add = (raw: string, label = "", description = "") => {
    const match = /^([GFYXRAKTCD])(\d{1,5})\.([0-7])$/i.exec(raw);
    if (!match || Number(match[2]) > 32767) return;
    const address = `${match[1].toUpperCase()}${Number(match[2])}.${match[3]}`;
    if (!signals.has(address)) signals.set(address, { address, label, description });
  };
  const walk = (node: LadderNode) => {
    if (node.kind === "contact") add(node.addr, node.label, node.description);
    else if (node.kind === "function") walk(node.input);
    else node.children.forEach(walk);
  };
  if (diagram?.status === "supported") {
    walk(diagram.logic);
    add(diagram.coil.addr, diagram.coil.label, diagram.coil.description);
  }
  // 그림으로 복원하지 못한 근거도 원본 명령에서 비트 주소를 수집한다.
  for (const instruction of diagram?.instructions ?? []) {
    for (const match of instruction.matchAll(/\b[GFYXRAKTCD]\d{1,5}\.[0-7]\b/gi)) add(match[0]);
  }
  return [...signals.values()];
}

export async function readTestSignals(addresses: string[], signal: AbortSignal) {
  let snapshot: PmcSnapshot | null = null;
  const values: PmcSnapshot["signals"] = [];
  // 서버의 요청당 128개 제한에 맞춰 순차 조회한다. 동일 PMC 스캔 시점은 보장하지 않는다.
  for (let start = 0; start < addresses.length; start += 128) {
    const response = await api.post<PmcSnapshot>("/api/ladder/test-signals", { addresses: addresses.slice(start, start + 128) }, {
      signal, timeout: 30000,
    });
    snapshot = response.data;
    values.push(...snapshot.signals);
  }
  return snapshot ? { ...snapshot, signals: values } : null;
}

export type MachineLadderNode = {
  type: string; address?: string; symbol?: string; comment?: string;
  children?: MachineLadderNode[]; input?: MachineLadderNode | null;
  sub?: number; subName?: string; operands?: { kind: string; value: string | number }[];
};
export type MachineLadderNet = { netIndex: number; program: string; outputs: MachineLadderNode[]; warnings: string[] };
export type MachineLadderDocument = { ladders: { name: string; label: string; nets: MachineLadderNet[] }[]; meta: { source: string; machine_code: string; filename: string } };

// 접점과 출력 코일을 함께 순회하므로 클릭한 위치에 관계없이 같은 주소를 찾는다.
export function getMachineNodeSignals(nodes: MachineLadderNode[]) {
  const addresses = new Set<string>();
  const walk = (node: MachineLadderNode) => {
    if (node.address && /^[GFYXRAKTCD]\d{1,5}\.[0-7]$/.test(node.address)) addresses.add(node.address);
    node.children?.forEach(walk);
    if (node.input) walk(node.input);
  };
  nodes.forEach(walk);
  return [...addresses];
}

export function getMachineSignals(nets: MachineLadderNet[]) {
  return getMachineNodeSignals(nets.flatMap(net => net.outputs));
}

export async function getTestLadder(signal: AbortSignal) {
  const response = await api.get<MachineLadderDocument>("/api/ladder/test-document", { signal, timeout: 15000 });
  return response.data;
}
