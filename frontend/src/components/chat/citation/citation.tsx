import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useState } from "react";
import type { ChatChunk, ChatMetadata, MessageItem } from "@/types/chatApi";
import ChunkAsset from "./chunkAsset";
import styles from "./citation.module.css";

type SelectedCitation = {
  messageId: string;
  chunkIndex: number;
} | null;

type CitationProps = {
  isCollapsed: boolean;
  onToggle: () => void;
  messages: MessageItem[];
  isLoading?: boolean;
  activeAssistantMessageId?: string | null;
  selectedCitation?: SelectedCitation;
  onCitationSelect?: (messageId: string, chunkIndex: number) => void;
};

// 외부 함수: 메시지 선택
// 기능/목적: 답변 메시지 목록에서 인용근거가 참조할 assistant 메시지를 찾는다.
// In: messages, activeAssistantMessageId / Out: MessageItem | undefined
function getLatestAssistantMessage(messages: MessageItem[]): MessageItem | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.metadata) return message;
  }
  return undefined;
}

function getActiveMessage(
  messages: MessageItem[],
  activeAssistantMessageId?: string | null
): MessageItem | undefined {
  if (activeAssistantMessageId) {
    const activeMessage = messages.find(
      (message) =>
        message.role === "assistant" &&
        String(message.message_id) === activeAssistantMessageId
    );
    if (activeMessage) return activeMessage;
  }

  return getLatestAssistantMessage(messages);
}

function getSelectedMessage(
  messages: MessageItem[],
  selectedCitation?: SelectedCitation
): MessageItem | undefined {
  if (!selectedCitation) return undefined;
  return messages.find(
    (message) => String(message.message_id) === selectedCitation.messageId
  );
}

function getSelectedChunk(
  messages: MessageItem[],
  selectedCitation?: SelectedCitation
): ChatChunk | undefined {
  const message = getSelectedMessage(messages, selectedCitation);
  const chunks = message?.metadata?.chunks ?? [];
  return chunks.find((chunk) => chunk.index === selectedCitation?.chunkIndex);
}

// 외부 함수: 참조/페이지 표시
// 기능/목적: 답변 본문의 [참조] 순서를 UI 라벨과 페이지 라벨로 변환한다.
// In: answerText, chunk metadata / Out: 참조 목록, 페이지 문자열
function getReferenceLabelMap(answerText = "") {
  const labelMap = new Map<number, number>();
  const citationPattern = /\[(?:chunk:)?(\d+)\]/gi;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(answerText)) !== null) {
    const chunkIndex = Number(match[1]);
    if (!labelMap.has(chunkIndex)) {
      labelMap.set(chunkIndex, labelMap.size + 1);
    }
  }

  return labelMap;
}

function getReferenceItems(answerText = "") {
  return Array.from(getReferenceLabelMap(answerText).entries())
    .map(([chunkIndex, label]) => ({ chunkIndex, label }))
    .sort((left, right) => left.label - right.label);
}

function toPageLabel(range: unknown): string | null {
  if (typeof range !== "string") return null;
  const normalized = range.trim();
  if (!normalized) return null;

  const rangeMatch = normalized.match(/^(\d+)\s*-\s*(\d+)$/);
  if (rangeMatch) {
    const [, start, end] = rangeMatch;
    return start === end ? `p.${start}` : `p.${start}~p.${end}`;
  }

  return /^\d+$/.test(normalized)
    ? `p.${normalized}`
    : `p.${normalized.replace(/\s*-\s*/g, "~")}`;
}

function getChunkPageLabel(chunk?: ChatChunk): string | null {
  const pageRange = typeof chunk?.metadata?.page_range === "string" ? chunk.metadata.page_range : null;
  const directLabel = toPageLabel(pageRange);
  if (directLabel) return directLabel;

  const pages = chunk?.metadata?.pages;
  if (pages && typeof pages === "object" && "range" in pages) {
    return toPageLabel(pages.range);
  }

  return null;
}

// 외부 함수: 포맷
// 기능/목적: metadata/chunk 원본을 개발 확인용 JSON 문자열로 안전하게 변환한다.
// In: unknown / Out: string
function formatJson(value?: unknown) {
  if (value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export default function Citation({
  isCollapsed,
  onToggle,
  messages,
  isLoading = false,
  activeAssistantMessageId,
  selectedCitation,
  onCitationSelect,
}: CitationProps) {
  // 내부 state
  // 기능/목적: 선택 답변의 metadata 원본 팝오버 열림 상태를 관리한다.
  const [isMetadataOpen, setIsMetadataOpen] = useState(false);

  // render 데이터
  // 기능/목적: 현재 답변, 선택 참조, 참조 버튼 목록을 렌더링에 맞는 값으로 계산한다.
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

  // render
  return (
    <div className={styles.citationRoot}>
      <div
        className={`${styles.citationHeader} ${
          isCollapsed ? styles.citationHeaderCollapsed : ""
        }`}
      >
        {!isCollapsed && <h2 className="pane-title">인용 근거</h2>}
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
              <h3>선택된 참조</h3>
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
