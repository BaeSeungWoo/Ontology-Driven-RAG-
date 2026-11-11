"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import ReactMarkdown from "react-markdown";
import AnalysisCircuits from "./citation/machineLadder/analysisCircuits";
import LadderAnswer from "./ladderAnswer";
import LadderSignalOverlay from "./citation/ladderSignalOverlay";
import { useMachine } from "@/components/machineProvider";
import type { ChatChunk } from "@/types/chatApi";
import { streamExplanation } from "@/services/explanationApi";
import type { MachineLadderNet } from "@/services/ladderApi";
import { Maximize2, Minimize2, Minus, Trash2 } from "lucide-react";
import FigureExplanation, { type FigureStatus } from "./figureExplanation";
import AlarmExplanation from "./alarmExplanation";
import figureStyles from "./figureExplanation.module.css";
import styles from "./figureExplanationProvider.module.css";
import PdfDocumentViewer from "./citation/pdfDocumentViewer";
import { resolveDocument } from "@/services/documentApi";
import type { ResolvedDocument } from "@/types/chatApi";
import type { CitationDocumentRequest } from "./citation/citationUtils";

type Figure = { messageId: number; assetPath: string; imageUrl: string; label: string };
type SavedFigure = Figure & { kind: "figure"; id: string; status: FigureStatus };
type SavedPdf = CitationDocumentRequest & { kind: "pdf"; id: string; label: string; document: ResolvedDocument };
export type AlarmAnalysis = { machine_code: string; machine_name: string; code: string; message: string; alarm_type: "system" | "operate"; detected_at: string; cleared_at: string | null };
type SavedAlarm = { kind: "alarm"; id: string; label: string; alarm: AlarmAnalysis; status: FigureStatus };
type LadderRequest = { evidence_count: number; message_id: number; machine_code: string; program: string; read_completed: string;
  signals: Record<string, 0 | 1 | null>; nets: MachineLadderNet[] };
export const LadderEvidence = createContext<ChatChunk[]>([]);
type LadderSource = { addresses: ReadonlySet<string>; chunks: ChatChunk[] };
type LadderTarget = { address: string; net?: Pick<MachineLadderNet, "program" | "netIndex"> };
type LadderNavigation = LadderTarget & { factoryId: string; machineCode: string };
type SavedLadder = LadderSource & Pick<LadderRequest, "nets" | "signals"> & {
  kind: "ladder"; id: string; label: string; status: FigureStatus; text: string;
  factoryId: string; machineCode: string; messageId: number;
};
const LadderContext = createContext<{
  open: (request: LadderRequest, source: LadderSource) => void;
  openAnswerSignal?: (address: string, messageId: number, chunks: ChatChunk[]) => void;
  navigation: LadderNavigation | null; clearNavigation: () => void; setHost: (element: HTMLDivElement | null) => void;
} | null>(null);

export function useLadderAnalysis() {
  const context = useContext(LadderContext);
  if (!context) throw new Error("FigureExplanationProvider is required");
  return context;
}

const AlarmContext = createContext<((alarm: AlarmAnalysis) => void) | null>(null);
const FigureContext = createContext<((figure: Figure) => void) | null>(null);
const PdfContext = createContext<((request: CitationDocumentRequest) => Promise<void>) | null>(null);

export function useAlarmExplanation() {
  const open = useContext(AlarmContext);
  if (!open) throw new Error("FigureExplanationProvider is required");
  return open;
}

export function usePdfDocument() {
  const open = useContext(PdfContext);
  if (!open) throw new Error("FigureExplanationProvider is required");
  return open;
}

export function useFigureExplanation() {
  const open = useContext(FigureContext);
  if (!open) throw new Error("FigureExplanationProvider is required");
  return open;
}

export default function FigureExplanationProvider({ children }: { children: ReactNode }) {
  const [figures, setFigures] = useState<(SavedFigure | SavedPdf | SavedAlarm | SavedLadder)[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [ladderHost, setLadderHost] = useState<HTMLDivElement | null>(null);
  const { factoryId, executionMachineCode, status } = useMachine();
  const [reopened, setReopened] = useState<Pick<SavedLadder, "factoryId" | "machineCode" | "messageId" | "chunks"> | null>(null);
  const [navigation, setNavigation] = useState<LadderNavigation | null>(null);
  const clearNavigation = useCallback(() => setNavigation(null), []);
  const requests = useRef(new Map<string, AbortController>());
  useEffect(() => {
    const pending = requests.current;
    return () => pending.forEach(controller => controller.abort());
  }, []);
  async function openLadder(payload: LadderRequest, source: LadderSource) {
    const id = JSON.stringify([factoryId, payload.message_id, payload.machine_code, payload.program, payload.read_completed,
      payload.nets.map(net => [net.program, net.netIndex])]);
    setActiveId(id);
    if (requests.current.has(id) || figures.some(item => item.id === id && item.kind === "ladder" && item.status !== "error")) return;
    const time = new Date(payload.read_completed).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
    const programs = [...new Set(payload.nets.map(net => net.program || payload.program))].join(", ");
    const label = [payload.machine_code, programs, time + " KST 수신분"].filter(Boolean).join(" · ");
    const controller = new AbortController();
    requests.current.set(id, controller);
    setFigures(current => [...current.filter(item => item.id !== id), { ...source, nets: payload.nets, signals: payload.signals, factoryId, messageId: payload.message_id, machineCode: payload.machine_code, kind: "ladder", id, label, status: "loading", text: "" }]);
    function update(text: string, status: FigureStatus) {
      if (!controller.signal.aborted) setFigures(current => current.map(item =>
        item.kind === "ladder" && item.id === id ? { ...item, text, status } : item));
    }
    try {
      const result = await streamExplanation("/api/ladder/explain", payload, controller.signal, partial => update(partial.answer, "loading"));
      update(result.answer, "complete");
    } catch (error) {
      update(error instanceof Error ? error.message : "래더 신호 분석에 실패했습니다.", "error");
    } finally {
      if (requests.current.get(id) === controller) requests.current.delete(id);
    }
  }
  const openAlarm = useCallback((alarm: AlarmAnalysis) => {
    const id = `alarm:${alarm.machine_code}:${alarm.alarm_type}:${alarm.code}:${alarm.detected_at}`;
    setFigures(current => current.some(item => item.id === id) ? current : [...current, {
      kind: "alarm", id, label: `${alarm.machine_code} · ${alarm.alarm_type === "system" ? "시스템" : "Operate"} · ${alarm.code}`, alarm, status: "loading",
    }]);
    setActiveId(id);
  }, []);
  const open = useCallback((figure: Figure) => {
    const id = `${figure.messageId}:${figure.assetPath}`;
    setFigures(current => current.some(item => item.id === id) ? current : [...current, { ...figure, kind: "figure", id, status: "loading" }]);
    setActiveId(id);
  }, []);

  const openPdf = useCallback(async (request: CitationDocumentRequest) => {
    const document = await resolveDocument(request.sourceDocName, request.pageRange);
    const id = `pdf:${request.documentKey}`;
    const label = `${document.document_name} · ${request.pageLabel ?? "PDF"}`;
    setFigures(current => current.some(item => item.id === id) ? current : [...current, { ...request, kind: "pdf", document, id, label }]);
    setActiveId(id);
  }, []);

  const updateStatus = useCallback((id: string, status: FigureStatus) => {
    setFigures(current => current.map(figure => figure.kind !== "pdf" && figure.id === id && figure.status !== status ? { ...figure, status } : figure));
  }, []);

  function remove(id: string) {
    requests.current.get(id)?.abort();
    requests.current.delete(id);
    setFigures(current => current.filter(item => item.id !== id));
    setActiveId(current => current === id ? null : current);
  }

  const dockItems = figures.filter(item => item.id !== activeId && (!ladderHost || item.kind === "ladder"));
  return (
    <FigureContext.Provider value={open}>
      <PdfContext.Provider value={openPdf}>
      <AlarmContext.Provider value={openAlarm}>
      <LadderContext.Provider value={{ open: openLadder, setHost: setLadderHost,
        openAnswerSignal: status === "ready" && executionMachineCode && executionMachineCode !== "ALL"
          ? (address, messageId, chunks) => {
            setReopened({ factoryId, machineCode: executionMachineCode, messageId, chunks });
            setNavigation({ factoryId, machineCode: executionMachineCode, address });
            setActiveId(null);
          } : undefined,
        navigation: navigation?.factoryId === factoryId && navigation.machineCode === executionMachineCode ? navigation : null, clearNavigation }}>
      {children}
      {reopened && reopened.machineCode === executionMachineCode && reopened.factoryId === factoryId &&
        <LadderSignalOverlay chunks={reopened.chunks} messageId={reopened.messageId}
          onClose={() => { setReopened(null); clearNavigation(); }} />}
      {figures.map(figure => {
        const title = figure.kind === "ladder" ? "래더 신호 분석" : figure.kind === "pdf" ? "PDF 문서" : figure.kind === "alarm" ? "알람 분석" : "그림 설명";
        const navigate = figure.kind === "ladder" && status === "ready" &&
          figure.machineCode === executionMachineCode && figure.factoryId === factoryId
          ? (target: LadderTarget) => {
            if (!ladderHost) setReopened(figure);
            setNavigation({ ...target, factoryId: figure.factoryId, machineCode: figure.machineCode });
            setActiveId(null);
          } : undefined;
        const panel = (
        <section key={figure.id} hidden={activeId !== figure.id}
          className={`${styles.window} ${figure.kind === "ladder" ? styles.ladderWindow : ""} ${figure.kind === "pdf" ? styles.pdfWindow : ""} ${figure.kind === "alarm" ? styles.alarmWindow : ""} ${expanded ? styles.expanded : ""}`}
          role="dialog" aria-label={`${title} · ${figure.label}`}>
          <header className={styles.header}>
            <strong title={figure.label}>{title} · {figure.label}</strong>
            <button type="button" aria-label={`${title} 축소`} title="하단에 보관" onClick={() => setActiveId(null)}><Minus size={16} /></button>
            <button type="button" aria-label={`${title} ${expanded ? "크기 복원" : "확대"}`} onClick={() => setExpanded(value => !value)}>
              {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
            </button>
            <button type="button" aria-label={`${title} 삭제`} title={`${title} 삭제`} onClick={() => remove(figure.id)}><Trash2 size={16} /></button>
          </header>
          <div className={styles.content}>{figure.kind === "pdf"
            ? <PdfDocumentViewer {...figure} variant="embedded" />
            : figure.kind === "alarm" ? <AlarmExplanation id={figure.id} alarm={figure.alarm} onStatusChange={updateStatus} />
            : figure.kind === "ladder" ? <div className={styles.ladderLayout}><div className={figureStyles.panel}>
              <div className={figureStyles.messages}>
                <p>{figure.label}</p>
                {figure.status === "loading" && <p role="status" className={figureStyles.loadingLabel}><span className={figureStyles.spinner} />신호 분석 중…</p>}
                {figure.status === "error" ? <p role="alert">{figure.text}</p>
                  : <div className={figureStyles.answer}>{navigate
                    ? <LadderAnswer text={figure.text} addresses={figure.addresses} onSelect={address => navigate({ address })} /> : <ReactMarkdown>{figure.text}</ReactMarkdown>}</div>}
              </div></div>
              <AnalysisCircuits nets={figure.nets} signals={figure.signals} onOpen={navigate && (net =>
                navigate({ net: { program: net.program, netIndex: net.netIndex }, address: net.outputs[0]?.address ?? "" }))} />
            </div>
            : <FigureExplanation {...figure} onStatusChange={updateStatus} />}</div>
        </section>
      );
        return figure.kind === "ladder" && ladderHost ? createPortal(panel, ladderHost, figure.id) : panel;
      })}
      {dockItems.length > 0 && createPortal(
        <aside className={`${styles.dock} ${figures.some(figure => figure.kind === "alarm") ? styles.alarmDock : ""}`} aria-label="보관된 설명 및 문서">
          {dockItems.map(figure => (
            <div key={figure.id} className={`${styles.saved} ${figure.kind === "alarm" ? styles.alarmSaved : ""}`}>
              <button type="button" title={figure.label} aria-label={`${figure.kind === "pdf" ? "PDF" : figure.kind === "alarm" ? "알람 AI" : "AI"} · ${figure.label}`} onClick={() => setActiveId(figure.id)}>
                <span className={styles.savedLabel}>{figure.kind === "pdf" ? "PDF" : figure.kind === "alarm" ? "알람 AI" : "AI"} · {figure.label}</span>
                {figure.kind !== "pdf" && <span className={styles.savedStatus} data-status={figure.status} role="status">
                  {figure.status === "loading" && <span className={figureStyles.spinner} aria-hidden="true" />}
                  {figure.status === "loading" ? "생성 중" : figure.status === "complete" ? "완료" : "오류"}
                </span>}
              </button>
              <button type="button" aria-label={`${figure.label} ${figure.kind === "ladder" ? "래더 신호 분석" : figure.kind === "pdf" ? "PDF 문서" : figure.kind === "alarm" ? "알람 분석" : "그림 설명"} 삭제`} onClick={() => remove(figure.id)}><Trash2 size={14} /></button>
            </div>
          ))}
        </aside>, ladderHost ?? document.body
      )}
      </LadderContext.Provider>
      </AlarmContext.Provider>
      </PdfContext.Provider>
    </FigureContext.Provider>
  );
}
