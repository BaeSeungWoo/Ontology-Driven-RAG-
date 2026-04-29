import Image from "next/image";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API_BASE_URL } from "@/services/api";
import styles from "./citation.module.css";

type ChunkAssetProps = {
  assetPath: string;
  assetType?: string | null;
  referenceLabel: string;
};

/**
 * 기능: metadata의 asset_path를 백엔드 정적 파일 URL로 변환한다.
 * 목적: data/pipeline 절대경로 등 다양한 저장 경로 표현을 브라우저에서 접근 가능한 /assets 경로로 맞춘다.
 * In: assetPath(string)
 * Out: asset URL(string)
 */
function toAssetUrl(assetPath: string) {
  const normalized = assetPath.replace(/\\/g, "/").replace(/^\/+/, "");
  if (/^https?:\/\//i.test(normalized)) return normalized;

  const lower = normalized.toLowerCase();
  const pipelineDataMarker = "/pipeline/data/";
  const pipelineDataIndex = lower.lastIndexOf(pipelineDataMarker);
  const normalizedAssetPath =
    pipelineDataIndex >= 0
      ? normalized.slice(pipelineDataIndex + pipelineDataMarker.length)
      : lower.startsWith("pipeline/data/")
        ? normalized.slice("pipeline/data/".length)
        : lower.startsWith("data/")
          ? normalized.slice("data/".length)
          : normalized;

  const encodedPath = normalizedAssetPath.split("/").map(encodeURIComponent).join("/");
  return `${API_BASE_URL}/assets/${encodedPath}`;
}

/**
 * 기능: 선택된 chunk의 이미지/표 asset을 렌더링한다.
 * 목적: 인용근거 패널 안에서 chunk 원문, 구조 데이터, 실제 자료를 함께 검토할 수 있게 한다.
 * In: assetPath, assetType(pictures | tables), referenceLabel
 * Out: 이미지 미리보기 또는 Markdown 표
 */
export default function ChunkAsset({
  assetPath,
  assetType,
  referenceLabel,
}: ChunkAssetProps) {
  const [tableMarkdown, setTableMarkdown] = useState<string | null>(null);
  const [tableLoadError, setTableLoadError] = useState(false);
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
  const assetUrl = toAssetUrl(assetPath);

  /**
   * 기능: 표 asset의 MD 파일을 /assets 정적 URL에서 fetch한다.
   * 목적: React 렌더링을 막지 않고 응답 도착 후 Markdown 표를 표시한다.
   * In: assetType, assetUrl
   * Out: tableMarkdown/tableLoadError 상태 갱신
   */
  useEffect(() => {
    if (assetType !== "tables") return;

    let isMounted = true;
    fetch(assetUrl, { cache: "no-store" })
      .then(async (response) => {
        const text = response.ok ? await response.text() : "";
        if (!isMounted) return;
        if (text.trim().length > 0) {
          setTableMarkdown(text);
        } else {
          setTableLoadError(true);
        }
      })
      .catch(() => {
        if (isMounted) setTableLoadError(true);
      });

    return () => {
      isMounted = false;
    };
  }, [assetType, assetUrl]);

  return (
    <div className={styles.chunkAsset}>
      <p className={styles.chunkAssetTitle}>이미지/표</p>
      {assetType === "pictures" ? (
        <button
          type="button"
          className={styles.chunkAssetImageButton}
          onClick={() => setPreviewImageUrl(assetUrl)}
          title="이미지 확대"
        >
          <Image
            className={styles.chunkAssetImage}
            src={assetUrl}
            alt={`${referenceLabel} 이미지`}
            width={320}
            height={220}
            unoptimized
          />
        </button>
      ) : assetType === "tables" ? (
        <div className={styles.chunkAssetMarkdown}>
          {tableMarkdown ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{tableMarkdown}</ReactMarkdown>
          ) : tableLoadError ? (
            <p>MD 파일을 불러오지 못했습니다.</p>
          ) : (
            <p>표 데이터를 불러오는 중입니다.</p>
          )}
        </div>
      ) : null}

      {previewImageUrl ? (
        <div
          className={styles.imagePreviewOverlay}
          role="dialog"
          aria-modal="true"
          aria-label={`${referenceLabel} 이미지 확대`}
          onClick={() => setPreviewImageUrl(null)}
        >
          <div className={styles.imagePreviewDialog} onClick={(event) => event.stopPropagation()}>
            <div className={styles.imagePreviewHeader}>
              <strong>{referenceLabel}</strong>
              <button type="button" onClick={() => setPreviewImageUrl(null)} aria-label="이미지 닫기">
                닫기
              </button>
            </div>
            <Image
              src={previewImageUrl}
              alt={`${referenceLabel} 확대 이미지`}
              width={920}
              height={700}
              unoptimized
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}
