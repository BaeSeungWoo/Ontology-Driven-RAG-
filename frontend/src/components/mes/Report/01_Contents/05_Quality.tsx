import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import { formatNumber, toNumber } from "../reportUtils";

/* ===================================================== */

type QualityHealthProps = {
  rows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
  managementPoint: string;
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

/* ===================================================== */

function formatDate(value: unknown): string {
  const dateValue = String(value ?? "");
  return /^\d{4}-\d{2}-\d{2}/.test(dateValue)
    ? dateValue.slice(0, 10).replace(/-/g, ".")
    : dateValue || "-";
}

/* ===================================================== */

export default function QualityHealth({
  rows,
  isLoading,
  errorMessage,
  managementPoint,
  isSummaryLoading,
  summaryErrorMessage,
}: QualityHealthProps) {
  const row = rows[0];
  const hasLatestDefect = Boolean(row?.LATEST_DEFECT_DATE);
  const latestDefectReason = String(row?.LATEST_DEFECT_REASON_NAME ?? "").trim();
  const metrics = [
    { label: "입고검사", value: row?.RECEIVING_INSPECTION_COUNT, unit: "건" },
    { label: "공정·최종검사", value: row?.PROCESS_FINAL_INSPECTION_COUNT, unit: "건" },
    {
      label: "최근 불량",
      displayValue: hasLatestDefect ? formatDate(row?.LATEST_DEFECT_DATE) : "발생 이력 없음",
      kind: "date",
    },
    { label: "교정 만료", value: row?.EXPIRED_CALIBRATION_COUNT, unit: "대", tone: "danger" },
    { label: "30일 내 교정", value: row?.DUE_WITHIN_30_DAYS_COUNT, unit: "대" },
    {
      label: "불량 원인",
      displayValue: hasLatestDefect ? latestDefectReason || "원인 미등록" : "발생 이력 없음",
      detail: hasLatestDefect && toNumber(row?.LATEST_DEFECT_QTY) > 0
        ? `${formatNumber(row?.LATEST_DEFECT_QTY)} EA`
        : "",
      kind: "text",
    },
  ];

  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.qualityHealthSection}`}
      aria-label="품질·계측기 관리"
    >
      <header className={styles.productionTrendHeading}>
        <h3>품질 · 계측기 관리</h3>
        {row && (
          <span>
            검사 7일 누계 {formatNumber(row.INSPECTION_COUNT_7D)}건 · 계측기 {formatNumber(row.CALIBRATION_EQUIPMENT_COUNT)}대
          </span>
        )}
      </header>

      {/* Loading  */}
      {isLoading && <p className={styles.reportMessage}>품질·계측기 데이터를 불러오는 중입니다.</p>}
      {!isLoading && errorMessage && <p className={styles.reportError}>{errorMessage}</p>}
      {!isLoading && !errorMessage && !row && (
        <p className={styles.reportMessage}>품질·계측기 관리 데이터가 없습니다.</p>
      )}

      {/* Contents */}
      {!isLoading && !errorMessage && row && (
        <>
          <div className={styles.qualityHealthMetrics}>
            {metrics.map((metric) => (
              <div key={metric.label} data-tone={metric.tone} data-kind={metric.kind}>
                <span>{metric.label}</span>
                <strong>
                  {metric.displayValue ?? formatNumber(metric.value)}
                  {metric.unit && <small>{metric.unit}</small>}
                </strong>
                {metric.detail && <small className={styles.qualityMetricDetail}>{metric.detail}</small>}
              </div>
            ))}
          </div>

          <article
            className={styles.managementPoint}
            data-tone="info"
          >
            <b>경영 포인트</b>
            {isSummaryLoading && <span>품질·계측기 데이터를 분석하는 중입니다.</span>}
            {!isSummaryLoading && summaryErrorMessage && <span>{summaryErrorMessage}</span>}
            {!isSummaryLoading && !summaryErrorMessage && managementPoint && (
              <span>{managementPoint}</span>
            )}
          </article>
        </>
      )}
    </section>
  );
}
