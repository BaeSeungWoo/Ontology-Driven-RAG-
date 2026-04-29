import Image from "next/image";
import { Image as ImageIcon, PanelRightClose, PanelRightOpen, Search } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE_URL } from "@/services/api";
import type { ChatChunk, ChatMetadata, MessageItem } from "@/types/chatApi";
import styles from "./chat.module.css";

type AssetItem = {
  path: string;
  chunkIndex?: number;
  type: "pictures" | "tables";
  document?: string;
  sourceDocName?: string;
  pageLabel?: string | null;
};

function getChunkMetaString(chunk: ChatChunk, key: string): string | null {
  const value = chunk.metadata?.[key];
  return typeof value === "string" && value.length > 0 ? value : null;
}

function getChunkAssetPath(chunk: ChatChunk): string | null {
  return getChunkMetaString(chunk, "asset_path");
}

function getChunkContainerType(chunk: ChatChunk): string | null {
  return getChunkMetaString(chunk, "container_type");
}

function getChunkSourceDocName(chunk: ChatChunk): string | null {
  return getChunkMetaString(chunk, "source_doc_name");
}

type ImagePreview = {
  url: string;
  label: string;
  sourceLabel?: string | null;
} | null;

type TablePreview = {
  path: string;
  label: string;
  sourceLabel?: string | null;
} | null;

type TableAssetContent = {
  text: string;
  source: "md" | "error" | "loading";
  url?: string;
  status?: number;
};

type AssetPanelProps = {
  activeAssistantMessage?: MessageItem;
  selectedCitation?: {
    messageId: string;
    chunkIndex: number;
  } | null;
  isLoading?: boolean;
  onCitationSelect: (messageId: string, chunkIndex: number) => void;
  // 부모 grid가 함께 줄어들어야 답변 영역이 넓어지므로 접힘 상태는 Chat에서 내려받는다.
  isCollapsed: boolean;
  onToggle: () => void;
};

type AssetPreviewModalProps = {
  title: string;
  sourceLabel?: string | null;
  ariaLabel: string;
  closeLabel: string;
  onClose: () => void;
  children: ReactNode;
};

function AssetPreviewModal({
  title,
  sourceLabel,
  ariaLabel,
  closeLabel,
  onClose,
  children,
}: AssetPreviewModalProps) {
  return (
    <div
      className={styles.assetPreviewOverlay}
      role="dialog"
      aria-modal="true"
      aria-label={ariaLabel}
      onClick={onClose}
    >
      <div className={styles.assetPreviewDialog} onClick={(event) => event.stopPropagation()}>
        <div className={styles.assetPreviewHeader}>
          <div className={styles.assetPreviewTitleBlock}>
            <strong>{title}</strong>
            {sourceLabel ? <span>{sourceLabel}</span> : null}
          </div>
          <button type="button" onClick={onClose} aria-label={closeLabel}>
            닫기
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/**
 * 기능: 이미지/표 asset 목록에서 중복 경로를 제거한다.
 * 목적: 같은 chunk 또는 metadata fallback에서 같은 자료가 여러 번 표시되지 않게 한다.
 * In: assets(AssetItem[])
 * Out: 중복 제거된 AssetItem[]
 */
function dedupeAssets(assets: AssetItem[]) {
  const seen = new Set<string>();
  return assets.filter((asset) => {
    const key = `${asset.type}:${asset.path}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

/**
 * 기능: metadata container_type이 화면 렌더링 가능한 asset 타입인지 판별한다.
 * 목적: 텍스트 chunk 등 렌더링 대상이 아닌 타입을 이미지/표 목록에서 제외한다.
 * In: value(unknown)
 * Out: pictures | tables 여부 결과
 */
function isSupportedAssetType(value: unknown): value is "pictures" | "tables" {
  return value === "pictures" || value === "tables";
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

  return /^\d+$/.test(normalized) ? `p.${normalized}` : `p.${normalized.replace(/\s*-\s*/g, "~")}`;
}

function getChunkPageLabel(chunk: ChatChunk): string | null {
  const directLabel = toPageLabel(getChunkMetaString(chunk, "page_range"));
  if (directLabel) return directLabel;

  const pages = chunk.metadata?.pages;
  if (pages && typeof pages === "object" && "range" in pages) {
    return toPageLabel(pages.range);
  }

  return null;
}

function toAssetItem(chunk: ChatChunk): AssetItem {
  const path = getChunkAssetPath(chunk);
  const type = getChunkContainerType(chunk);
  return {
    path: path as string,
    chunkIndex: chunk.index,
    type: type as "pictures" | "tables",
    document: chunk.document,
    sourceDocName: getChunkSourceDocName(chunk) ?? undefined,
    pageLabel: getChunkPageLabel(chunk),
  };
}

/**
 * 기능: active metadata에서 이미지/표 asset 목록을 추출한다.
 * 목적: 사용된 chunk 우선, 전체 chunk, legacy images/tables 순서로 화면 표시 대상을 결정한다.
 * In: metadata(ChatMetadata)
 * Out: AssetItem[]
 */
function getChunkAssets(metadata?: ChatMetadata): AssetItem[] {
  const usedChunkAssets =
    metadata?.used_chunks
      ?.filter(
        (chunk) =>
          typeof getChunkAssetPath(chunk) === "string" &&
          (getChunkAssetPath(chunk)?.length ?? 0) > 0 &&
          isSupportedAssetType(getChunkContainerType(chunk))
      )
      .map(toAssetItem) ?? [];

  if (usedChunkAssets.length > 0) {
    return dedupeAssets(usedChunkAssets);
  }

  const chunkAssets =
    metadata?.chunks
      ?.filter(
        (chunk) =>
          typeof getChunkAssetPath(chunk) === "string" &&
          (getChunkAssetPath(chunk)?.length ?? 0) > 0 &&
          isSupportedAssetType(getChunkContainerType(chunk))
      )
      .map(toAssetItem) ?? [];

  if (chunkAssets.length > 0) {
    return dedupeAssets(chunkAssets);
  }

  const imageAssets = Array.isArray(metadata?.images)
    ? metadata.images
        .filter((assetPath): assetPath is string => typeof assetPath === "string")
        .map((path) => ({ path, type: "pictures" as const }))
    : [];
  const tableAssets = Array.isArray(metadata?.tables)
    ? metadata.tables
        .filter((assetPath): assetPath is string => typeof assetPath === "string")
        .map((path) => ({ path, type: "tables" as const }))
    : [];

  return dedupeAssets([...imageAssets, ...tableAssets]);
}

/**
 * 기능: 답변 본문에 등장한 chunk 번호를 참조 표시 번호로 매핑한다.
 * 목적: 답변의 [참조N], 이미지/표 caption, 인용근거 배지가 같은 번호 체계를 쓰게 한다.
 * In: answerText(string)
 * Out: Map<chunkIndex, referenceLabelNumber>
 */
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

/**
 * 기능: 이미지/표 asset을 답변의 참조 등장 순서대로 정렬한다.
 * 목적: 오른쪽 이미지/표 영역이 답변의 참조 흐름과 같은 순서로 보이게 한다.
 * In: assets, referenceLabelMap
 * Out: 참조 순서가 적용된 AssetItem[]
 */
function sortAssetsByReferenceOrder(assets: AssetItem[], referenceLabelMap: Map<number, number>) {
  return [...assets].sort((left, right) => {
    const leftOrder =
      left.chunkIndex !== undefined ? referenceLabelMap.get(left.chunkIndex) : undefined;
    const rightOrder =
      right.chunkIndex !== undefined ? referenceLabelMap.get(right.chunkIndex) : undefined;

    if (leftOrder !== undefined && rightOrder !== undefined) {
      return leftOrder - rightOrder;
    }
    if (leftOrder !== undefined) return -1;
    if (rightOrder !== undefined) return 1;
    return 0;
  });
}

/**
 * 기능: metadata의 asset 경로를 브라우저에서 접근 가능한 정적 파일 URL로 변환한다.
 * 목적: data/pipeline 내부 경로 등 다양한 입력 경로를 /assets 기반 URL로 맞춘다.
 * In: imagePath(string)
 * Out: asset URL(string)
 */
function toAssetUrl(imagePath: string) {
  const normalized = imagePath.replace(/\\/g, "/").replace(/^\/+/, "");
  if (/^https?:\/\//i.test(normalized)) return normalized;

  const lower = normalized.toLowerCase();
  const pipelineDataMarker = "/pipeline/data/";
  const pipelineDataIndex = lower.lastIndexOf(pipelineDataMarker);
  const assetPath =
    pipelineDataIndex >= 0
      ? normalized.slice(pipelineDataIndex + pipelineDataMarker.length)
      : lower.startsWith("pipeline/data/")
        ? normalized.slice("pipeline/data/".length)
        : lower.startsWith("data/")
          ? normalized.slice("data/".length)
          : normalized;

  const encodedPath = assetPath.split("/").map(encodeURIComponent).join("/");
  return `${API_BASE_URL}/assets/${encodedPath}`;
}

/**
 * 기능: 답변 우측 개발용 이미지/표 패널을 렌더링한다.
 * 목적: active assistant metadata의 asset을 참조 순서대로 보여주고 클릭 시 인용근거와 연동한다.
 * In: activeAssistantMessage, onCitationSelect
 * Out: 이미지/표 목록, 이미지/표 확대 모달
 */
export default function AssetPanel({
  activeAssistantMessage,
  selectedCitation,
  isLoading = false,
  onCitationSelect,
  isCollapsed,
  onToggle,
}: AssetPanelProps) {
  const [imagePreview, setImagePreview] = useState<ImagePreview>(null);
  const [tablePreview, setTablePreview] = useState<TablePreview>(null);
  const [tableMarkdownByPath, setTableMarkdownByPath] = useState<Record<string, TableAssetContent>>({});
  const assetFigureRefs = useRef<Record<number, HTMLElement | null>>({});
  const referenceLabelMap = useMemo(
    () => getReferenceLabelMap(activeAssistantMessage?.content ?? ""),
    [activeAssistantMessage?.content]
  );
  const assetItems = useMemo(
    () =>
      sortAssetsByReferenceOrder(
        getChunkAssets(activeAssistantMessage?.metadata),
        referenceLabelMap
      ),
    [activeAssistantMessage?.metadata, referenceLabelMap]
  );
  const tableAssetKey = useMemo(
    () =>
      assetItems
        .filter((asset) => asset.type === "tables")
        .map((asset) => asset.path)
        .join("\n"),
    [assetItems]
  );

  /**
   * 기능: 표 asset의 MD 파일을 /assets 정적 URL에서 fetch한다.
   * 목적: React 렌더링을 막지 않고 응답 완료 후 Markdown 표를 표시한다.
   * In: assetItems/tableAssetKey
   * Out: tableMarkdownByPath 갱신
   */
  useEffect(() => {
    const tableAssets = assetItems.filter((asset) => asset.type === "tables");
    if (tableAssets.length === 0) return;

    let isMounted = true;
    tableAssets.forEach(async (asset) => {
      const url = toAssetUrl(asset.path);
      try {
        const response = await fetch(url, { cache: "no-store" });
        const text = response.ok ? await response.text() : "";
        if (isMounted) {
          setTableMarkdownByPath((prev) => {
            if (prev[asset.path] !== undefined) return prev;
            return {
              ...prev,
              [asset.path]:
                text.trim().length > 0
                  ? { text, source: "md", url, status: response.status }
                  : {
                      text: "MD 파일을 불러오지 못했습니다.",
                      source: "error",
                      url,
                      status: response.status,
                    },
            };
          });
        }
      } catch {
        if (isMounted) {
          setTableMarkdownByPath((prev) => {
            if (prev[asset.path] !== undefined) return prev;
            return {
              ...prev,
              [asset.path]: { text: "MD 파일을 불러오지 못했습니다.", source: "error", url },
            };
          });
        }
      }
    });

    return () => {
      isMounted = false;
    };
  }, [assetItems, tableAssetKey]);

  /**
   * 기능: 확대 모달을 ESC 키로 닫는다.
   * 목적: 이미지/표 확대 보기에서 마우스 없이도 빠르게 원래 화면으로 돌아가게 한다.
   * In: imagePreview/tablePreview 변경, Escape keydown
   * Out: preview 상태 초기화
   */
  useEffect(() => {
    if (!imagePreview && !tablePreview) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setImagePreview(null);
      setTablePreview(null);
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [imagePreview, tablePreview]);

  /**
   * 기능: 선택된 참조가 바뀌면 해당 asset 카드로 자연스럽게 이동한다.
   * 목적: 답변/인용근거에서 참조를 눌렀을 때 오른쪽 패널에서도 같은 자료를 즉시 찾게 한다.
   * In: selectedCitation, activeAssistantMessage
   * Out: 선택 카드 scrollIntoView
   */
  useEffect(() => {
    if (!selectedCitation || !activeAssistantMessage) return;
    if (selectedCitation.messageId !== String(activeAssistantMessage.message_id)) return;
    const target = assetFigureRefs.current[selectedCitation.chunkIndex];
    target?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selectedCitation, activeAssistantMessage]);

  // 접힘 상태에서는 header와 토글 버튼만 남겨 영역 폭을 최소화한다.
  const assetPanelClassName = `${styles.chatAssetPanel} ${
    isCollapsed ? styles.chatAssetPanelCollapsed : ""
  }`;
  const assetPanelLabel = "이미지/표 영역";
  const assetToggleLabel = isCollapsed
    ? "이미지/표 영역 펼치기"
    : "이미지/표 영역 접기";
  const assetCount = assetItems.length;
  const activeTableContent = tablePreview
    ? tableMarkdownByPath[tablePreview.path] ?? {
        text: "표 데이터를 불러오는 중입니다.",
        source: "loading" as const,
        url: toAssetUrl(tablePreview.path),
      }
    : null;

  const selectAssetCitation = (asset: AssetItem) => {
    if (activeAssistantMessage && asset.chunkIndex !== undefined) {
      onCitationSelect(String(activeAssistantMessage.message_id), asset.chunkIndex);
    }
  };

  const getAssetLabel = (asset: AssetItem, index: number) =>
    asset.chunkIndex !== undefined
      ? `참조${referenceLabelMap.get(asset.chunkIndex) ?? asset.chunkIndex}`
      : asset.type === "tables" ? `표${index + 1}` : `이미지 ${index + 1}`;
  const getSourceLabel = (asset: AssetItem) =>
    [asset.sourceDocName, asset.pageLabel].filter(Boolean).join(" · ") || null;

  return (
    <aside className={assetPanelClassName} aria-label={assetPanelLabel}>
      <div className={styles.chatAssetPanelHeader}>
        <span className={styles.chatAssetPanelTitleGroup}>
          <ImageIcon className={styles.chatAssetPanelTitleIcon} aria-hidden="true" />
          <span className={styles.chatAssetPanelLabel}>{assetPanelLabel}</span>
          <span className={styles.chatAssetPanelInlineCount} aria-label={`자료 ${assetCount}개`}>
            {assetCount}
          </span>
        </span>
        <button
          type="button"
          className={styles.chatAssetToggle}
          onClick={() => {
            if (!isCollapsed) {
              setImagePreview(null);
              setTablePreview(null);
            }
            onToggle();
          }}
          aria-expanded={!isCollapsed}
          aria-label={assetToggleLabel}
        >
          {isCollapsed ? (
            <PanelRightOpen className={styles.chatAssetToggleIcon} aria-hidden="true" />
          ) : (
            <PanelRightClose className={styles.chatAssetToggleIcon} aria-hidden="true" />
          )}
        </button>
      </div>

      {!isCollapsed && (assetItems.length > 0 ? (
        <div className={styles.chatAssetGrid}>
          {assetItems.map((asset, index) => {
            const assetLabel = getAssetLabel(asset, index);
            const sourceLabel = getSourceLabel(asset);
            const isActiveAsset =
              asset.chunkIndex !== undefined &&
              selectedCitation?.chunkIndex === asset.chunkIndex &&
              selectedCitation.messageId === String(activeAssistantMessage?.message_id);

            return (
              <figure
                className={`${styles.chatAssetFigure} ${
                  asset.chunkIndex !== undefined ? styles.chatAssetFigureClickable : ""
                } ${isActiveAsset ? styles.chatAssetFigureActive : ""}`}
                key={`${asset.type}-${asset.path}-${index}`}
                ref={(element) => {
                  if (asset.chunkIndex === undefined) return;
                  assetFigureRefs.current[asset.chunkIndex] = element;
                }}
                onClick={() => selectAssetCitation(asset)}
              >
                {asset.type === "pictures" ? (
                  <button
                    type="button"
                    className={styles.chatAssetImageButton}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectAssetCitation(asset);
                      setImagePreview({
                        url: toAssetUrl(asset.path),
                        label: assetLabel,
                        sourceLabel,
                      });
                    }}
                    title="이미지 확대"
                  >
                    <Image
                      src={toAssetUrl(asset.path)}
                      alt={`metadata 이미지 ${index + 1}`}
                      width={260}
                      height={180}
                      unoptimized
                    />
                  </button>
                ) : (
                  <button
                    type="button"
                    className={styles.chatAssetTableButton}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectAssetCitation(asset);
                      setTablePreview({
                        path: asset.path,
                        label: assetLabel,
                        sourceLabel,
                      });
                    }}
                    title="표 확대"
                  >
                    <div className={styles.chatAssetTablePreview}>
                      {tableMarkdownByPath[asset.path]?.source === "md" ? (
                        <div className={styles.chatAssetTableBlur} aria-hidden="true">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {tableMarkdownByPath[asset.path].text}
                          </ReactMarkdown>
                        </div>
                      ) : null}
                      <span className={styles.chatAssetTableIcon} aria-hidden="true">
                        표
                      </span>
                      <span className={styles.chatAssetTableText}>
                        {tableMarkdownByPath[asset.path]?.source === "md" ? (
                          <>
                            <span>표 크게 보기</span>
                            <Search className={styles.chatAssetTableTextIcon} aria-hidden="true" />
                          </>
                        ) : (
                          "표 데이터 로딩 중"
                        )}
                      </span>
                      {tableMarkdownByPath[asset.path]?.source !== "md" ? (
                        <span className={styles.chatAssetTableLoadingBar} aria-hidden="true" />
                      ) : null}
                    </div>
                  </button>
                )}
                <figcaption>
                  <button
                    type="button"
                    className={styles.chatAssetCaptionButton}
                    onClick={(event) => {
                      event.stopPropagation();
                      selectAssetCitation(asset);
                    }}
                  >
                    {assetLabel}
                  </button>
                </figcaption>
              </figure>
            );
          })}
        </div>
      ) : isLoading && activeAssistantMessage ? (
        <div className={styles.chatAssetGrid} aria-hidden="true">
          {Array.from({ length: 2 }).map((_, index) => (
            <div className={styles.chatAssetSkeletonCard} key={`asset-skeleton-${index}`}>
              <div className={styles.chatAssetSkeletonPreview} />
              <div className={styles.chatAssetSkeletonCaption} />
            </div>
          ))}
        </div>
      ) : (
        <p className={styles.chatAssetPanelHint}>
          질문 답변에 사용된 이미지 또는 표가 여기에 표시됩니다.
        </p>
      ))}

      {!isCollapsed && imagePreview ? (
        <AssetPreviewModal
          title={imagePreview.label}
          sourceLabel={imagePreview.sourceLabel}
          ariaLabel={`${imagePreview.label} 이미지 확대`}
          closeLabel="이미지 닫기"
          onClose={() => setImagePreview(null)}
        >
          <Image
            src={imagePreview.url}
            alt={`${imagePreview.label} 확대 이미지`}
            width={920}
            height={700}
            unoptimized
          />
        </AssetPreviewModal>
      ) : null}

      {!isCollapsed && tablePreview && activeTableContent ? (
        <AssetPreviewModal
          title={tablePreview.label}
          sourceLabel={tablePreview.sourceLabel}
          ariaLabel={`${tablePreview.label} 표 확대`}
          closeLabel="표 닫기"
          onClose={() => setTablePreview(null)}
        >
          <div className={styles.tablePreviewBody}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{activeTableContent.text}</ReactMarkdown>
          </div>
        </AssetPreviewModal>
      ) : null}
    </aside>
  );
}
