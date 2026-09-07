import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import { formatNumber, toNumber } from "../reportUtils";

/* ===================================================== */

type ProductionResultTrendProps = {
  rows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
  managementPoint: string;
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

/* ===================================================== */

function formatDate(value: unknown): string {
  const date = String(value ?? "");
  return /^\d{4}-\d{2}-\d{2}/.test(date) ? date.slice(5, 10) : date || "-";
}

/* ===================================================== */

export default function ProductionResultTrend({
  rows,
  isLoading,
  errorMessage,
  managementPoint,
  isSummaryLoading,
  summaryErrorMessage,
}: ProductionResultTrendProps) {
  const trendRows = [...rows]
    .sort((left, right) => String(left.RESULT_DATE ?? "").localeCompare(String(right.RESULT_DATE ?? "")))
    .slice(-14);
  const averageResultCount = toNumber(trendRows[0]?.AVERAGE_RESULT_COUNT)
    || (trendRows.length > 0
      ? trendRows.reduce((sum, row) => sum + toNumber(row.RESULT_COUNT), 0) / trendRows.length
      : 0);
  const maximumResultCount = toNumber(trendRows[0]?.MAX_RESULT_COUNT)
    || Math.max(0, ...trendRows.map((row) => toNumber(row.RESULT_COUNT)));
  const minimumResultCount = trendRows.length > 0
    ? toNumber(trendRows[0]?.MIN_RESULT_COUNT)
    : 0;
  const latestResultCount = toNumber(trendRows.at(-1)?.RESULT_COUNT);
  const trendTone = latestResultCount >= averageResultCount ? "good" : "warn";
  const fallbackManagementPoint = trendRows.length > 0
    ? `최근 14일 평균 ${formatNumber(averageResultCount, 1)}건이며, 최대 ${formatNumber(maximumResultCount)}건입니다.`
    : "";

  return (
    <section className={styles.reportSection} aria-label="생산 실적 추이">

      <header className={styles.productionTrendHeading}>
        <h3>생산 실적 추이</h3>
        <span>최근 14일 · 자동생성 제외</span>
      </header>
      
      {/* loading */}
      {isLoading && <p className={styles.reportMessage}>생산 실적 추이를 불러오는 중입니다.</p>}
      {!isLoading && errorMessage && <p className={styles.reportError}>{errorMessage}</p>}
      {!isLoading && !errorMessage && trendRows.length === 0 && (
        <p className={styles.reportMessage}>생산 실적 추이 데이터가 없습니다.</p>
      )}

      {/* Contents */}
      {!isLoading && !errorMessage && trendRows.length > 0 && (
        <>
          <div className={styles.productionTrendChart} role="img" aria-label="최근 14일 생산 실적 건수 막대 차트">
            {trendRows.map((row) => {
              const resultCount = toNumber(row.RESULT_COUNT);
              const barHeight = maximumResultCount > 0 ? resultCount / maximumResultCount * 84 : 0;
              const tone = resultCount > 0 && resultCount < averageResultCount * 0.6 ? "low" : "normal";

              return (
                <div
                  key={String(row.RESULT_DATE)}
                  className={styles.productionTrendColumn}
                  title={`${String(row.RESULT_DATE).slice(0, 10)} · ${formatNumber(resultCount)}건`}
                >
                  <div className={styles.productionTrendBarArea}>
                    <b style={{ bottom: `calc(${barHeight}% + 4px)` }}>
                      {formatNumber(resultCount)}
                    </b>
                    <i data-tone={tone} style={{ height: `${barHeight}%` }} />
                  </div>
                  <small>{formatDate(row.RESULT_DATE)}</small>
                </div>
              );
            })}
          </div>

          <div className={styles.productionTrendSummary}>
            <span>평균 <strong>{formatNumber(averageResultCount, 1)}</strong>건/일</span>
            <span>최대 <strong>{formatNumber(maximumResultCount)}</strong>건 · 최소 <strong>{formatNumber(minimumResultCount)}</strong>건</span>
          </div>

          <article className={styles.managementPoint} data-tone={trendTone}>
            <b>경영 포인트</b>
            {isSummaryLoading && <span>생산 실적 추이를 분석하는 중입니다.</span>}
            {!isSummaryLoading && summaryErrorMessage && <span>{summaryErrorMessage}</span>}
            {!isSummaryLoading && !summaryErrorMessage && (
              <span>{managementPoint || fallbackManagementPoint}</span>
            )}
          </article>
        </>
      )}
    </section>
  );
}
