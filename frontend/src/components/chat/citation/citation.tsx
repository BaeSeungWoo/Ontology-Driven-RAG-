import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronUp, FileText, Network, Workflow } from "lucide-react";
import type { ChatChunk, ChatMetadata, MessageItem } from "@/types/chatApi";
import ChunkAsset from "./chunkAsset";
import CmsEvidence, { getAlarmManualDescription, getAlarmManualDefinition, parseCmsEvidence } from "./cmsEvidence";
import {
  getActiveMessage,
  getCitationDocumentRequest,
  getChunkPageLabel,
  getMessageReferenceItems,
  getSelectedChunk,
  getSelectedMessage,
  type CitationDocumentRequest,
  type SelectedCitation,
} from "./citationUtils";
import styles from "./citation.module.css";

const evidenceTabs = ["문서 근거", "도면·래더", "지식그래프"] as const;
function getEvidenceTab(chunk?: ChatChunk) {
  return chunk?.metadata.ladder_diagram || chunk?.metadata.container_type === "ladder"
    ? "도면·래더" : "문서 근거";
}

type CitationProps = {
  canExplainFigure?: boolean;
  isNewQuestion?: boolean;
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
  canExplainFigure = false,
  isNewQuestion = false,
  isCollapsed,
  onToggle,
  messages,
  isLoading = false,
  activeAssistantMessageId,
  selectedCitation,
  onCitationSelect,
  onDocumentOpen,
}: CitationProps) {
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [documentError, setDocumentError] = useState<string | null>(null);
  const [isDocumentLoading, setIsDocumentLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<string>("문서 근거");

  const activeMessage = getActiveMessage(messages, activeAssistantMessageId);
  const activeMetadata: ChatMetadata | undefined = activeMessage?.metadata;
  const selectedMessage = getSelectedMessage(messages, selectedCitation);
  const selectedChunk = getSelectedChunk(messages, selectedCitation);
  const selectedAlarmCode = selectedChunk?.metadata?.source_kind === "cms"
    ? parseCmsEvidence(selectedChunk.document)?.code : null;
  const selectedChunks = selectedMessage?.metadata?.chunks?.length
    ? selectedMessage.metadata.chunks : selectedMessage?.metadata?.used_chunks ?? [];
  const alarmManual = selectedAlarmCode ? selectedChunks.find(chunk =>
    chunk.metadata.source_kind === "manual" && (chunk.metadata.matched_alarm_code === selectedAlarmCode
      || (Array.isArray(chunk.metadata.matched_alarm_codes) && chunk.metadata.matched_alarm_codes.includes(selectedAlarmCode))))
    ?? selectedChunks.find(chunk => chunk.metadata.source_kind === "manual"
      && getAlarmManualDescription(chunk.document, selectedAlarmCode)) : undefined;
  const alarmDescription = alarmManual ? getAlarmManualDescription(alarmManual.document, selectedAlarmCode) : null;
  const referenceLabelMap = new Map(getMessageReferenceItems(selectedMessage ?? activeMessage).map((item) => [item.chunkIndex, item.label]));
  const referenceItems = getMessageReferenceItems(activeMessage);
  const activeChunks = activeMetadata?.chunks?.length
    ? activeMetadata.chunks
    : activeMetadata?.used_chunks ?? [];
  const referenceCards = referenceItems.map((item) => ({
    ...item,
    chunk: activeChunks.find((chunk) => chunk.index === item.chunkIndex)
      ?? activeMetadata?.used_chunks?.find((chunk) => chunk.index === item.chunkIndex),
  }));
  const visibleCards = referenceCards.filter(card => getEvidenceTab(card.chunk) === activeTab);
  const EmptyIcon = activeTab === "도면·래더" ? Workflow : activeTab === "지식그래프" ? Network : FileText;
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
  const selectedDocumentRequest = getCitationDocumentRequest(
    messages,
    selectedCitation,
    activeAssistantMessageId
  );

  useEffect(() => {
    setDocumentError(null);
  }, [selectedCitation?.messageId, selectedCitation?.chunkIndex]);

  useEffect(() => {
    setActiveTab("문서 근거");
  }, [activeMessage?.message_id, isNewQuestion]);

  useEffect(() => {
    if (selectedChunk) setActiveTab(getEvidenceTab(selectedChunk));
  }, [selectedChunk]);

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

  const referenceDetail = selectedCitation ? (
    <div className={styles.inlineReferenceDetail}>
          {selectedChunk ? (
            <div className={styles.chunkCard}>
              {selectedChunk.metadata?.source_kind === "cms" ? <>
                <CmsEvidence text={selectedChunk.document} manualDescription={alarmDescription}
                  manualDefinition={alarmManual ? getAlarmManualDefinition(alarmManual.document, selectedAlarmCode) : null} />
                {selectedAlarmCode ? <div className={styles.chunkBodyBlock}>
                  <p className={styles.chunkBodyTitle}>연결된 장비 매뉴얼</p>
                  {alarmManual ? <>
                    <p>{String(alarmManual.metadata.source_doc_name)} · {getChunkPageLabel(alarmManual) ?? "페이지 미기록"}</p>
                    <p className={styles.chunkDocument}>{alarmManual.document}</p>
                    <button type="button" className={styles.openDocumentButton}
                      onClick={() => onCitationSelect?.(selectedCitation.messageId, alarmManual.index)}>
                      매뉴얼 근거 보기
                    </button>
                  </> : <p>이 답변에서 해당 알람 코드와 일치하는 장비 매뉴얼 근거를 찾지 못했습니다.</p>}
                </div> : null}
              </> : <>
              {selectedDocumentRequest && <div className={styles.documentActionBlock}>
                <button
                  type="button"
                  className={styles.openDocumentButton}
                  onClick={handleOpenDocument}
                  disabled={isDocumentLoading}
                >
                  {isDocumentLoading ? "문서 여는 중..." : "참고문서 열기"}
                </button>
                {documentError ? (
                  <p className={styles.documentError}>{documentError}</p>
                ) : null}
              </div>}
              <div className={styles.chunkBodyBlock}>
                <p className={styles.chunkBodyTitle}>근거 원문</p>
                <p className={styles.chunkDocument}>{selectedChunk.document}</p>
              </div>
              {selectedAssetPath ? (
                <ChunkAsset
                  figureMessageId={canExplainFigure ? Number(selectedCitation.messageId) : undefined}
                  key={`${selectedChunk.index}-${selectedAssetPath}`}
                  assetPath={selectedAssetPath}
                  assetType={selectedContainerType}
                  referenceLabel={selectedReferenceLabel ?? "선택 참조"}
                />
              ) : null}
              </>}
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
  ) : null;

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
          </div>
        ) : null}
        <button
          type="button"
          className={styles.citationToggle}
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? "인용 근거 펼치기" : "인용 근거 접기"}
        >
          {isCollapsed ? <ChevronDown size={19} aria-hidden="true" /> : <ChevronUp size={19} aria-hidden="true" />}
        </button>
      </div>

      <div
        className={`${styles.citationBody} ${
          isCollapsed ? styles.citationBodyHidden : styles.citationBodyVisible
        }`}
        aria-hidden={isCollapsed}
      >
        {!isCollapsed && <>
          <div className={styles.emptyTabs} aria-label="근거 유형">
            {evidenceTabs.map(tab => {
              const count = referenceCards.filter(card => getEvidenceTab(card.chunk) === tab).length;
              return <button key={tab} type="button" aria-pressed={activeTab === tab}
                onClick={() => { setActiveTab(tab); setIsDetailOpen(false); }}>
                {tab}{count > 0 && <span className={styles.citationCount}>{count}</span>}
              </button>;
            })}
          </div>
          {visibleCards.length === 0 && <div className={styles.emptyEvidence} role="status">
            <EmptyIcon size={50} strokeWidth={1.6} aria-hidden="true" />
            <h3>{isNewQuestion ? "답변의 근거가 모이는 곳" : `${activeTab}가 없습니다`}</h3>
            <p>{isLoading ? "답변과 관련된 근거를 확인하고 있어요." : isNewQuestion ? <>
              질문하면 관련 문서와 도면,<br />지식 연결을 여기에서 확인할 수 있어요.
            </> : "이 답변에 연결된 근거가 있으면 여기에 표시됩니다."}</p>
          </div>}
        </>}
        {activeMessage && visibleCards.length > 0 ? (
          <section className={styles.referenceCardsArea} aria-label="참조 요약">
            {visibleCards[0]?.additional && (
              <p className={styles.referenceCardsTitle}>추가 검색된 래더 근거</p>
            )}
            <div className={styles.referenceCardList}>
              {visibleCards.map(({ chunkIndex, label, chunk, additional }, index) => {
                const isActive = selectedCitation?.messageId === String(activeMessage.message_id) && selectedCitation.chunkIndex === chunkIndex;
                const isExpanded = isActive && isDetailOpen;
                const sourceDocName =
                  typeof chunk?.metadata?.source_doc_name === "string"
                    ? chunk.metadata.source_doc_name
                    : "문서명 없음";
                const isCms = chunk?.metadata?.source_kind === "cms";
                const score = chunk?.similarity ?? chunk?.rrf_score ?? chunk?.bm25_score;

                return (
                  <Fragment key={chunkIndex}>
                    {additional && index > 0 && !visibleCards[index - 1].additional && (
                      <p className={styles.referenceCardsTitle}>추가 검색된 래더 근거</p>
                    )}
                  <article className={`${styles.referenceCard} ${isExpanded ? styles.referenceCardActive : ""}`}>
                  <button
                    type="button"
                    className={styles.referenceCardToggle}
                    onClick={() =>
                      handleReferenceCardClick(String(activeMessage.message_id), chunkIndex)
                    }
                    aria-expanded={isExpanded}
                  >
                    <span className={styles.referenceCardMeta}>
                      <span className={styles.referenceCardNumber}>{label}</span>
                      <span className={styles.referenceCardScore}>
                        {isCms ? "DB 조회 근거" : typeof score === "number"
                          ? `관련도 ${score.toFixed(3)}`
                          : chunk?.retrieval_rank
                            ? `검색 순위 ${chunk.retrieval_rank}`
                            : "참조 문서"}
                      </span>
                      {!isCms && <span className={styles.referenceCardPage}>
                        {getChunkPageLabel(chunk) ?? "페이지 -"}
                      </span>}
                      {isExpanded ? <ChevronUp size={16} aria-hidden="true" /> : <ChevronDown size={16} aria-hidden="true" />}
                    </span>
                    <strong className={styles.referenceCardDocument}>{sourceDocName}</strong>
                  </button>
                  {isExpanded && referenceDetail}
                  </article>
                  </Fragment>
                );
              })}
            </div>
          </section>
        ) : null}



      </div>


    </div>
  );
}
