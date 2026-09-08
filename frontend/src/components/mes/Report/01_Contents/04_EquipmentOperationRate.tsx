import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import { getReportDateKey, toNumber } from "../reportUtils";

/* ===================================================== */

type EquipmentOperationRateProps = {
  equipmentWeeklyRows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
  managementPoint: string;
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

/* ===================================================== */

function formatRate(value: unknown): string {
  return `${toNumber(value).toFixed(1).replace(/\.0$/, "")}%`;
}

function positiveRateTone(rate: number): "good" | "watch" | "warn" {
  if (rate < 30) return "warn";
  if (rate < 70) return "watch";
  return "good";
}

function equipmentRateTone(rate: number): "good" | "watch" | "warn" | "idle" {
  if (rate === 0) return "idle";
  return positiveRateTone(rate);
}

/* ===================================================== */

export default function EquipmentOperationRate({
  equipmentWeeklyRows,
  isLoading,
  errorMessage,
  managementPoint,
  isSummaryLoading,
  summaryErrorMessage,
}: EquipmentOperationRateProps) {
  const latestEquipmentOperationDate = equipmentWeeklyRows.reduce(
    (latestDate, row) => {
      const baseDate = getReportDateKey(row.BASE_DATE);
      return baseDate > latestDate ? baseDate : latestDate;
    },
    "",
  );
  const latestEquipmentOperationRows = equipmentWeeklyRows.filter(
    (row) => getReportDateKey(row.BASE_DATE) === latestEquipmentOperationDate,
  );
  const equipmentSummaryRate = latestEquipmentOperationRows.length > 0
    ? latestEquipmentOperationRows.reduce((sum, row) => sum + toNumber(row.OPERATION_RATE), 0)
      / latestEquipmentOperationRows.length
    : 0;
  const equipmentTone = positiveRateTone(equipmentSummaryRate);
  const topMachineOperationRateRows = [...latestEquipmentOperationRows]
    .sort((left, right) => toNumber(right.OPERATION_RATE) - toNumber(left.OPERATION_RATE))
    .slice(0, 8);
  const equipmentOperationCounts = latestEquipmentOperationRows.reduce<{
    good: number;
    watch: number;
    warn: number;
    idle: number;
  }>(
    (counts, row) => {
      const rate = toNumber(row.OPERATION_RATE);
      if (rate === 0) counts.idle += 1;
      else if (rate < 30) counts.warn += 1;
      else if (rate < 70) counts.watch += 1;
      else counts.good += 1;
      return counts;
    },
    { good: 0, watch: 0, warn: 0, idle: 0 },
  );
  const equipmentOperationDate = getReportDateKey(topMachineOperationRateRows[0]?.BASE_DATE);

  return (
    <section className={styles.reportSection} aria-label="설비별 가동률">
      {/* title */}
      <header className={styles.productionTrendHeading}>
        <h3>설비별 가동률 TOP 8</h3>
        <span>{equipmentOperationDate || "-"}</span>
      </header>

      {/* legend */}
      <div className={styles.equipmentOperationLegend} aria-label="가동률 상태 기준">
        <span data-tone="good"><i />70% 이상({equipmentOperationCounts.good}대)</span>
        <span data-tone="watch"><i />30~69.9%({equipmentOperationCounts.watch}대)</span>
        <span data-tone="warn"><i />0% 초과~30% 미만({equipmentOperationCounts.warn}대)</span>
        <span data-tone="idle"><i />정지({equipmentOperationCounts.idle}대)</span>
      </div>

      {/* loading */}
      {isLoading && <p className={styles.reportMessage}>설비별 가동률 데이터를 불러오는 중입니다.</p>}
      {errorMessage && <p className={styles.reportError}>{errorMessage}</p>}
      {!isLoading && !errorMessage && topMachineOperationRateRows.length === 0 && (
        <p className={styles.reportMessage}>설비별 가동률 데이터가 없습니다.</p>
      )}

      {/* Contents */}
      {!isLoading && !errorMessage && topMachineOperationRateRows.length > 0 && (
        <>
          <div className={styles.equipmentOperationList}>
            {topMachineOperationRateRows.map((row) => {
              const rate = toNumber(row.OPERATION_RATE);
              const tone = equipmentRateTone(rate);
              return (
                <div key={String(row.MACHINE_CODE ?? row.MACHINE_NAME)} className={styles.equipmentOperationRow}>
                  <span>{String(row.MACHINE_NAME ?? "-")}</span>
                  <div className={styles.equipmentOperationTrack}>
                    <i data-tone={tone} style={{ width: `${Math.min(100, Math.max(0, rate))}%` }} />
                  </div>
                  <b>{formatRate(rate)}</b>
                </div>
              );
            })}
          </div>
          
          <article className={styles.managementPoint} data-tone={equipmentTone}>
            <b>경영 포인트</b>
            {isSummaryLoading && <span>설비별 가동률을 분석하는 중입니다.</span>}
            {!isSummaryLoading && summaryErrorMessage && <span>{summaryErrorMessage}</span>}
            {!isSummaryLoading && !summaryErrorMessage && managementPoint && <span>{managementPoint}</span>}
          </article>
        </>
      )}
    </section>
  );
}
