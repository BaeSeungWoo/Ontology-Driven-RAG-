"use client";

import { ExternalLink, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import type { ResolvedDocument } from "@/types/chatApi";
import { findHighlightItemIndexes } from "./pdfHighlightMatcher";
import styles from "./citation.module.css";

type PdfDocumentViewerProps = {
  document: ResolvedDocument;
  pageLabel: string | null;
  chunkText: string;
  referenceLabel: string;
  onClose: () => void;
  variant?: "modal" | "panel";
  isUpdating?: boolean;
};

type HighlightRect = {
  left: number;
  top: number;
  width: number;
  height: number;
};

type TextItemLike = {
  str?: string;
  transform?: number[];
  width?: number;
  height?: number;
};

type PdfJsModule = {
  Util: {
    transform: (left: number[], right: number[]) => number[];
  };
  GlobalWorkerOptions: {
    workerSrc: string;
  };
  getDocument: (options: { url: string }) => {
    promise: Promise<PdfDocumentLike>;
  };
};

type PdfDocumentLike = {
  numPages: number;
  getPage: (pageNumber: number) => Promise<PdfPageLike>;
  destroy?: () => Promise<void>;
};

type PdfPageLike = {
  getViewport: (options: { scale: number }) => PdfViewportLike;
  render: (options: { canvasContext: CanvasRenderingContext2D; viewport: PdfViewportLike }) => {
    cancel: () => void;
    promise: Promise<unknown>;
  };
  getTextContent: () => Promise<{ items: TextItemLike[] }>;
};

type PdfViewportLike = {
  width: number;
  height: number;
  scale: number;
  transform: number[];
};

function getPdfUrl(assetUrl: string) {
  return assetUrl.split("#")[0];
}

function getPageNumber(document: ResolvedDocument) {
  return document.page && document.page > 0 ? document.page : 1;
}

function toHighlightRect(
  pdfjs: Pick<PdfJsModule, "Util">,
  viewport: PdfViewportLike,
  item: TextItemLike
): HighlightRect | null {
  if (!item.transform || item.transform.length < 6) return null;

  const transform = pdfjs.Util.transform(viewport.transform, item.transform);
  const fontHeight = Math.hypot(transform[2], transform[3]);
  const width = Math.max((item.width || 0) * viewport.scale, 2);
  const height = Math.max(fontHeight, (item.height || 0) * viewport.scale, 8);

  return {
    left: transform[4],
    top: transform[5] - height,
    width,
    height,
  };
}

export default function PdfDocumentViewer({
  document,
  pageLabel,
  chunkText,
  referenceLabel,
  onClose,
  variant = "modal",
  isUpdating = false,
}: PdfDocumentViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState({ width: 0, height: 0 });
  const [highlightRects, setHighlightRects] = useState<HighlightRect[]>([]);
  const showLoading = isLoading || isUpdating;

  useEffect(() => {
    let isMounted = true;
    let renderTask: { cancel: () => void; promise: Promise<unknown> } | null = null;
    let loadedPdf: PdfDocumentLike | null = null;

    async function renderPage() {
      setIsLoading(true);
      setLoadError(null);
      setHighlightRects([]);

      try {
        const pdfjs = (await import("pdfjs-dist/build/pdf.mjs")) as unknown as PdfJsModule;
        pdfjs.GlobalWorkerOptions.workerSrc = new URL(
          "pdfjs-dist/build/pdf.worker.mjs",
          import.meta.url
        ).toString();

        const loadingTask = pdfjs.getDocument({
          url: getPdfUrl(document.asset_url),
        });
        const pdf = await loadingTask.promise;
        loadedPdf = pdf;
        const pageNumber = Math.min(getPageNumber(document), pdf.numPages);
        const page = await pdf.getPage(pageNumber);
        const viewport = page.getViewport({ scale: 1.35 });
        const canvas = canvasRef.current;
        if (!canvas || !isMounted) return;

        const context = canvas.getContext("2d");
        if (!context) throw new Error("Canvas context is not available.");

        const pixelRatio = window.devicePixelRatio || 1;
        canvas.width = Math.floor(viewport.width * pixelRatio);
        canvas.height = Math.floor(viewport.height * pixelRatio);
        canvas.style.width = `${viewport.width}px`;
        canvas.style.height = `${viewport.height}px`;
        context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);

        setPageSize({ width: viewport.width, height: viewport.height });

        renderTask = page.render({ canvasContext: context, viewport });
        await renderTask.promise;

        const textContent = await page.getTextContent();
        const textItems = textContent.items as TextItemLike[];
        const matchedIndexes = new Set(findHighlightItemIndexes(textItems, chunkText));
        const rects = textItems
          .map((item, index) => (matchedIndexes.has(index) ? toHighlightRect(pdfjs, viewport, item) : null))
          .filter((rect): rect is HighlightRect => rect !== null);

        if (!isMounted) return;
        setHighlightRects(rects);
      } catch (error) {
        if (!isMounted) return;
        if (error instanceof Error && error.name === "RenderingCancelledException") return;
        console.error("PDF.js render failed", error);
        setLoadError("PDF 형광펜 렌더링에 실패해 기본 뷰어로 표시합니다.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    renderPage();

    return () => {
      isMounted = false;
      renderTask?.cancel();
      if (typeof loadedPdf?.destroy === "function") {
        void loadedPdf.destroy();
      }
    };
  }, [chunkText, document]);

  const content = (
    <div
      className={`${styles.pdfModalDialog} ${
        variant === "panel" ? styles.pdfPanelDialog : ""
      }`}
      onClick={(event) => event.stopPropagation()}
    >
      <div className={styles.pdfModalHeader}>
        <div className={styles.pdfModalTitleBlock}>
          <strong>{document.document_name}</strong>
          <span>{pageLabel ?? "페이지 정보 없음"}</span>
        </div>
        <div className={styles.pdfModalActions}>
          <a
            className={styles.pdfModalIconButton}
            href={document.asset_url}
            target="_blank"
            rel="noreferrer"
            aria-label="새 탭에서 열기"
            title="새 탭에서 열기"
          >
            <ExternalLink aria-hidden="true" />
          </a>
          <button
            type="button"
            className={styles.pdfModalIconButton}
            onClick={onClose}
            aria-label="닫기"
            title="닫기"
          >
            <X aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className={styles.pdfViewerStage}>
        {showLoading ? (
          <div className={styles.pdfViewerLoadingShade} role="status" aria-live="polite">
            <span className={styles.pdfViewerSpinner} aria-hidden="true" />
            <span>{isUpdating ? "선택한 참조 문서를 불러오는 중입니다." : "PDF 페이지를 불러오는 중입니다."}</span>
          </div>
        ) : null}
        {loadError ? <div className={styles.pdfViewerStatus}>{loadError}</div> : null}
        {loadError ? (
          <iframe
            className={styles.pdfFallbackFrame}
            src={document.asset_url}
            title={document.document_name}
          />
        ) : (
          <div
            className={styles.pdfCanvasWrap}
            style={{ width: pageSize.width || undefined, height: pageSize.height || undefined }}
          >
            <canvas ref={canvasRef} className={styles.pdfCanvas} />
            <div className={styles.pdfHighlightLayer} aria-hidden="true">
              {highlightRects.map((rect, index) => (
                <span
                  key={`${rect.left}-${rect.top}-${index}`}
                  className={styles.pdfHighlightMark}
                  style={{
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height,
                  }}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={styles.pdfChunkHighlight}>
        <div className={styles.pdfChunkHighlightHeader}>
          <span>{referenceLabel}</span>
          <strong>{highlightRects.length > 0 ? "PDF 형광펜 적용" : "선택 청크"}</strong>
        </div>
        <p>{chunkText}</p>
      </div>
    </div>
  );

  if (variant === "panel") {
    return content;
  }

  return (
    <div
      className={styles.pdfModalOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="참고문서"
      onClick={onClose}
    >
      {content}
    </div>
  );
}
