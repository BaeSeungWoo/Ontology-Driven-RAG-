import { FileText, Lightbulb, MousePointerClick, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";
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
}: CitationProps) {
  const [isMetadataOpen, setIsMetadataOpen] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);

  const activeMessage = getActiveMessage(messages, activeAssistantMessageId);
  const activeMetadata: ChatMetadata | undefined = activeMessage?.metadata;
  const selectedMessage = getSelectedMessage(messages, selectedCitation);
  const selectedChunk = getSelectedChunk(messages, selectedCitation);
  const labelSourceText = selectedMessage?.content ?? activeMessage?.content ?? "";
  const referenceLabelMap = getReferenceLabelMap(labelSourceText);
  const referenceItems = getReferenceItems(activeMessage?.content ?? "");
  const selectedReferenceLabel =
    selectedCitation && referenceLabelMap.has(selectedCitation.chunkIndex)
      ? `참조${referenceLabelMap.get(selectedCitation.chunkIndex)}`
      : selectedCitation
        ? `참조${selectedCitation.chunkIndex}`
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
  const hasMetadata = activeMetadata !== undefined;
  const selectedDocumentRequest = getCitationDocumentRequest(
    messages,
    selectedCitation,
    activeAssistantMessageId
  );

  useEffect(() => {
    setDocumentError(null);
  }, [selectedCitation?.messageId, selectedCitation?.chunkIndex]);

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
            <Lightbulb className={styles.citationTitleIcon} aria-hidden="true" />
          </div>
        ) : null}
        <button
          type="button"
          className={styles.citationToggle}
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? "인용 근거 펼치기" : "인용 근거 접기"}
        >
          {isCollapsed ? (
            <PanelLeftOpen className={styles.citationToggleIcon} aria-hidden="true" />
          ) : (
            <PanelLeftClose className={styles.citationToggleIcon} aria-hidden="true" />
          )}
        </button>
      </div>

      <div
        className={`${styles.citationBody} ${
          isCollapsed ? styles.citationBodyHidden : styles.citationBodyVisible
        }`}
        aria-hidden={isCollapsed}
      >
        <section className={styles.referenceArea} aria-label="인용 근거">
          <div className={styles.referenceHeader}>
            <div className={styles.referenceHeadingGroup}>
              <h3 className={styles.referenceTitleWithIcon}>
                <MousePointerClick className={styles.referenceTitleIcon} aria-hidden="true" />
                <span>선택한 참조</span>
              </h3>
              <div className={styles.referenceBadges}>
                {selectedReferenceLabel ? <span>{selectedReferenceLabel}</span> : null}
              </div>
            </div>
            <div className={styles.metadataBadgeWrap}>
              <button
                type="button"
                className={styles.metadataBadge}
                onClick={() => setIsMetadataOpen((prev) => !prev)}
                disabled={!hasMetadata}
                aria-expanded={isMetadataOpen}
                aria-label="metadata 보기"
              >
                metadata
              </button>
              {isMetadataOpen && hasMetadata ? (
                <div className={styles.metadataPopover} role="dialog" aria-label="metadata">
                  <pre className={styles.metadataPre}>{formatJson(activeMetadata)}</pre>
                </div>
              ) : null}
            </div>
          </div>

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
                  <FileText className={styles.openDocumentIcon} aria-hidden="true" />
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
        </section>

        {activeMessage && referenceItems.length > 0 ? (
          <nav className={styles.referenceNav} aria-label="다른 참조 선택">
            <p className={styles.referenceNavTitle}>다른 참조</p>
            <div className={styles.referenceNavList}>
              {referenceItems.map((item) => {
                const isActive = selectedCitation?.chunkIndex === item.chunkIndex;
                return (
                  <button
                    key={item.chunkIndex}
                    type="button"
                    className={`${styles.referenceNavButton} ${
                      isActive ? styles.referenceNavButtonActive : ""
                    }`}
                    onClick={() =>
                      onCitationSelect?.(String(activeMessage.message_id), item.chunkIndex)
                    }
                    aria-pressed={isActive}
                  >
                    참조{item.label}
                  </button>
                );
              })}
            </div>
          </nav>
        ) : null}
      </div>

    </div>
  );
}
