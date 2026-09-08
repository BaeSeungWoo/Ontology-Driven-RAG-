import { useEffect, useState, type ReactNode } from "react";
import type { ChatMetadata, MessageItem } from "@/types/chatApi";
import ChunkAsset from "./chunkAsset";
import {
  formatJson,
  getActiveMessage,
  getCitationDocumentRequest,
  getChunkPageLabel,
  getReferenceItems,
  getReferenceLabelMap,
  getSelectedChunk,
  getSelectedMessage,
  type CitationDocumentRequest,
  type SelectedCitation,
} from "./citationUtils";
import styles from "./citation.module.css";

type CitationProps = {
  isCollapsed: boolean;
  onToggle: () => void;
  messages: MessageItem[];
  isLoading?: boolean;
  activeAssistantMessageId?: string | null;
  selectedCitation?: SelectedCitation;
  onCitationSelect?: (messageId: string, chunkIndex: number) => void;
  onDocumentOpen?: (documentRequest: CitationDocumentRequest) => Promise<void> | void;
  onDetailClose?: () => void;
  documentOverlay?: ReactNode;
};

export default function Citation({
  isCollapsed,
  onToggle,
  messages,
  isLoading = false,
  activeAssistantMessageId,
  selectedCitation,
  onCitationSelect,
  onDocumentOpen,
  onDetailClose,
  documentOverlay,
}: CitationProps) {
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);

  const activeMessage = getActiveMessage(messages, activeAssistantMessageId);
  const activeMetadata: ChatMetadata | undefined = activeMessage?.metadata;
  const selectedMessage = getSelectedMessage(messages, selectedCitation);
  const selectedChunk = getSelectedChunk(messages, selectedCitation);
  const labelSourceText = selectedMessage?.content ?? activeMessage?.content ?? "";
  const referenceLabelMap = getReferenceLabelMap(labelSourceText);
  const referenceItems = getReferenceItems(activeMessage?.content ?? "");
  const activeChunks = activeMetadata?.chunks?.length
    ? activeMetadata.chunks
    : activeMetadata?.used_chunks ?? [];
  const referenceCards = referenceItems.map((item) => ({
    ...item,
    chunk: activeChunks.find((chunk) => chunk.index === item.chunkIndex),
  }));
  const selectedReferenceNumber = selectedCitation
    ? (referenceLabelMap.get(selectedCitation.chunkIndex) ?? selectedCitation.chunkIndex)
    : null;
  const selectedReferenceLabel = selectedReferenceNumber !== null
    ? `참조${selectedReferenceNumber}`
    : null;
  const selectedAssetPath =
    typeof selectedChunk?.metadata?.asset_path === "string" &&
    selectedChunk.metadata.asset_path.length > 0
      ? selectedChunk.metadata.asset_path
      : null;
  const selectedContainerType =
    typeof selectedChunk?.metadata?.container_type === "string"
      ? selectedChunk.metadata.container_type
      : undefined;
  const selectedSourceDocName =
    typeof selectedChunk?.metadata?.source_doc_name === "string"
      ? selectedChunk.metadata.source_doc_name
      : undefined;
  const selectedPageLabel = getChunkPageLabel(selectedChunk);
  const selectedDocumentRequest = getCitationDocumentRequest(
    messages,
    selectedCitation,
    activeAssistantMessageId
  );

  useEffect(() => {
    setDocumentError(null);
  }, [selectedCitation?.messageId, selectedCitation?.chunkIndex]);

  useEffect(() => {
    if (isCollapsed || !selectedCitation) {
      setIsDetailOpen(false);
      return;
    }

    setIsDetailOpen(true);
  }, [isCollapsed, selectedCitation]);

  const handleReferenceCardClick = (messageId: string, chunkIndex: number) => {
    const isSelected =
      selectedCitation?.messageId === messageId &&
      selectedCitation.chunkIndex === chunkIndex;

    if (isSelected) {
      if (isDetailOpen) onDetailClose?.();
      setIsDetailOpen((prev) => !prev);
      return;
    }

    onCitationSelect?.(messageId, chunkIndex);
  };

  const handleOpenDocument = async () => {
    if (!selectedDocumentRequest) return;

    setIsDocumentLoading(true);
    setDocumentError(null);

    try {
      await onDocumentOpen?.(selectedDocumentRequest);
    } catch {
      setDocumentError("참고문서를 찾을 수 없습니다.");
    } finally {
      setIsDocumentLoading(false);
    }
  };

  return (
    <div className={styles.citationRoot}>
      <div
        className={`${styles.citationHeader} ${
          isCollapsed ? styles.citationHeaderCollapsed : ""
        }`}
      >
        {!isCollapsed ? (
          <div className={styles.citationTitleGroup}>
            <h2 className="pane-title">인용 근거</h2>
            {referenceCards.length > 0 ? (
              <span className={styles.citationCount}>{referenceCards.length}</span>
            ) : null}
          </div>
        ) : null}
        <button
          type="button"
          className={styles.citationToggle}
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? "인용 근거 펼치기" : "인용 근거 접기"}
        >
          <span aria-hidden="true">{isCollapsed ? "+" : "−"}</span>
        </button>
      </div>

      <div
        className={`${styles.citationBody} ${
          isCollapsed ? styles.citationBodyHidden : styles.citationBodyVisible
        }`}
        aria-hidden={isCollapsed}
      >
        {activeMessage && referenceCards.length > 0 ? (
          <section className={styles.referenceCardsArea} aria-label="참조 요약">
            <p className={styles.referenceCardsTitle}>답변에 사용된 참조</p>
            <div className={styles.referenceCardList}>
              {referenceCards.map(({ chunkIndex, label, chunk }) => {
                const isActive = selectedCitation?.chunkIndex === chunkIndex;
                const sourceDocName =
                  typeof chunk?.metadata?.source_doc_name === "string"
                    ? chunk.metadata.source_doc_name
                    : "문서명 없음";
                const score = chunk?.similarity ?? chunk?.rrf_score ?? chunk?.bm25_score;

                return (
                  <button
                    key={chunkIndex}
                    type="button"
                    className={`${styles.referenceCard} ${
                      isActive ? styles.referenceCardActive : ""
                    }`}
                    onClick={() =>
                      handleReferenceCardClick(String(activeMessage.message_id), chunkIndex)
                    }
                    aria-pressed={isActive}
                  >
                    <span className={styles.referenceCardMeta}>
                      <span className={styles.referenceCardNumber}>{label}</span>
                      <span className={styles.referenceCardScore}>
                        {typeof score === "number"
                          ? `관련도 ${score.toFixed(3)}`
                          : chunk?.retrieval_rank
                            ? `검색 순위 ${chunk.retrieval_rank}`
                            : "참조 문서"}
                      </span>
                      <span className={styles.referenceCardPage}>
                        {getChunkPageLabel(chunk) ?? "페이지 -"}
                      </span>
                    </span>
                    <strong className={styles.referenceCardDocument}>{sourceDocName}</strong>
                    <span className={styles.referenceCardSummary}>
                      {chunk?.document ?? "참조 내용을 불러오는 중입니다."}
                    </span>
                    <span className={styles.referenceCardAction}>
                      {isActive && isDetailOpen ? "상세 닫기" : "상세 보기"}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        ) : null}

        {!isCollapsed && isDetailOpen && selectedCitation ? (
          <section
            className={styles.referenceOverlay}
            role="dialog"
            aria-label="선택한 참조 상세"
          >
          <div className={styles.referenceHeader}>
            <div className={styles.referenceHeadingGroup}>
              <h3 className={styles.referenceTitleWithIcon}>
                <span>선택한 참조</span>
              </h3>
              <div className={styles.referenceBadges}>
                {selectedReferenceNumber !== null ? (
                  <span className={styles.selectedReferenceNumber}>
                    {selectedReferenceNumber}
                  </span>
                ) : null}
              </div>
            </div>
            <div className={styles.referenceHeaderActions}>
              <button
                type="button"
                className={styles.referenceCloseButton}
                onClick={() => {
                  setIsDetailOpen(false);
                  onDetailClose?.();
                }}
                aria-label="선택한 참조 닫기"
              >
                ×
              </button>
            </div>
          </div>

          <div className={styles.referenceOverlayBody}>
          {selectedChunk ? (
            <div className={styles.chunkCard}>
              <div className={styles.chunkMetaGrid}>
                <p className={styles.chunkTitle}>
                  <span className={styles.chunkMetaLabel}>문서명</span>
                  <span>{selectedSourceDocName ?? "unknown"}</span>
                </p>
                <p className={styles.chunkPageRange}>
                  <span className={styles.chunkMetaLabel}>페이지</span>
                  <span>{selectedPageLabel ?? "-"}</span>
                </p>
              </div>
              <div className={styles.documentActionBlock}>
                <button
                  type="button"
                  className={styles.openDocumentButton}
                  onClick={handleOpenDocument}
                  disabled={!selectedDocumentRequest || isDocumentLoading}
                >
                  {isDocumentLoading ? "문서 여는 중..." : "참고문서 열기"}
                </button>
                {documentError ? (
                  <p className={styles.documentError}>{documentError}</p>
                ) : null}
              </div>
              <div className={styles.chunkBodyBlock}>
                <p className={styles.chunkBodyTitle}>청크 원문</p>
                <p className={styles.chunkDocument}>{selectedChunk.document}</p>
              </div>
              <pre className={styles.chunkPre}>{formatJson(selectedChunk)}</pre>
              {selectedAssetPath ? (
                <ChunkAsset
                  key={`${selectedChunk.index}-${selectedAssetPath}`}
                  assetPath={selectedAssetPath}
                  assetType={selectedContainerType}
                  referenceLabel={selectedReferenceLabel ?? "선택 참조"}
                />
              ) : null}
            </div>
          ) : isLoading && activeMessage ? (
            <div className={styles.chunkCardSkeleton} aria-hidden="true">
              <div className={styles.skeletonLine} />
              <div className={`${styles.skeletonLine} ${styles.skeletonLineShort}`} />
              <div className={styles.skeletonBlock} />
              <div className={styles.skeletonBlockTall} />
            </div>
          ) : (
            <p className="pane-placeholder">
              답변의 [참조]를 클릭하면 해당 청크가 표시됩니다.
            </p>
          )}
          </div>
          </section>
        ) : null}

      </div>

      {documentOverlay ? (
        <section className={styles.pdfSideOverlay} aria-label="참고문서 PDF">
          {documentOverlay}
        </section>
      ) : null}

    </div>
  );
}
