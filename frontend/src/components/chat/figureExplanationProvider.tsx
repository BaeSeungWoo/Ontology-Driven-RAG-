"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { Maximize2, Minimize2, Minus, Trash2 } from "lucide-react";
import FigureExplanation, { type FigureStatus } from "./figureExplanation";
import figureStyles from "./figureExplanation.module.css";
import styles from "./figureExplanationProvider.module.css";
import PdfDocumentViewer from "./citation/pdfDocumentViewer";
import { resolveDocument } from "@/services/documentApi";
import type { ResolvedDocument } from "@/types/chatApi";
import type { CitationDocumentRequest } from "./citation/citationUtils";

type Figure = { messageId: number; assetPath: string; imageUrl: string; label: string };
type SavedFigure = Figure & { kind: "figure"; id: string; status: FigureStatus };
type SavedPdf = CitationDocumentRequest & { kind: "pdf"; id: string; label: string; document: ResolvedDocument };
const FigureContext = createContext<((figure: Figure) => void) | null>(null);
const PdfContext = createContext<((request: CitationDocumentRequest) => Promise<void>) | null>(null);

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
  const [figures, setFigures] = useState<(SavedFigure | SavedPdf)[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);
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
    setFigures(current => current.map(figure => figure.kind === "figure" && figure.id === id && figure.status !== status ? { ...figure, status } : figure));
  }, []);

  function remove(id: string) {
    setFigures(current => current.filter(item => item.id !== id));
    setActiveId(current => current === id ? null : current);
  }

  return (
    <FigureContext.Provider value={open}>
      <PdfContext.Provider value={openPdf}>
      {children}
      {figures.map(figure => {
        const title = figure.kind === "pdf" ? "PDF 문서" : "그림 설명";
        return (
        <section key={figure.id} hidden={activeId !== figure.id}
          className={`${styles.window} ${figure.kind === "pdf" ? styles.pdfWindow : ""} ${expanded ? styles.expanded : ""}`}
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
            : <FigureExplanation {...figure} onStatusChange={updateStatus} />}</div>
        </section>
      ); })}
      {figures.some(figure => figure.id !== activeId) && (
        <aside className={styles.dock} aria-label="보관된 그림 설명">
          {figures.filter(figure => figure.id !== activeId).map(figure => (
            <div key={figure.id} className={styles.saved}>
              <button type="button" title={figure.label} aria-label={`${figure.kind === "pdf" ? "PDF" : "AI"} · ${figure.label}`} onClick={() => setActiveId(figure.id)}>
                <span className={styles.savedLabel}>{figure.kind === "pdf" ? "PDF" : "AI"} · {figure.label}</span>
                {figure.kind === "figure" && <span className={styles.savedStatus} data-status={figure.status} role="status">
                  {figure.status === "loading" && <span className={figureStyles.spinner} aria-hidden="true" />}
                  {figure.status === "loading" ? "생성 중" : figure.status === "complete" ? "완료" : "오류"}
                </span>}
              </button>
              <button type="button" aria-label={`${figure.label} ${figure.kind === "pdf" ? "PDF 문서" : "그림 설명"} 삭제`} onClick={() => remove(figure.id)}><Trash2 size={14} /></button>
            </div>
          ))}
        </aside>
      )}
      </PdfContext.Provider>
    </FigureContext.Provider>
  );
}
