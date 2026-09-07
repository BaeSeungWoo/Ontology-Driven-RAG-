import type { MesViewRow } from "@/services/mesApi";
import styles from "../../../mes.module.css";
import { formatNumber, toNumber } from "../../reportUtils";

function getDateKey(value: unknown): string {
  return String(value ?? "").slice(0, 10);
}

function getDelta(currentValue: unknown, previousValue: unknown): number {
  return toNumber(currentValue) - toNumber(previousValue);
}

function formatDelta(currentValue: unknown, previousValue: unknown): string {
  const delta = getDelta(currentValue, previousValue);
  return `(${delta > 0 ? "+" : ""}${formatNumber(delta, 2)})`;
}

function getDeltaDirection(currentValue: unknown, previousValue: unknown): "up" | "down" | "same" {
  const delta = toNumber(currentValue) - toNumber(previousValue);
  if (delta > 0) return "up";
  if (delta < 0) return "down";
  return "same";
}

export default function ProductionResult({ rows }: { rows: MesViewRow[] }) {
  const row = rows.reduce<MesViewRow | undefined>((latestRow, currentRow) => {
    if (!latestRow) return currentRow;
    return getDateKey(currentRow.REPORT_DATE) > getDateKey(latestRow.REPORT_DATE)
      ? currentRow
      : latestRow;
  }, undefined);
  const previousRow = rows.reduce<MesViewRow | undefined>((latestPreviousRow, currentRow) => {
    if (!row || getDateKey(currentRow.REPORT_DATE) >= getDateKey(row.REPORT_DATE)) {
      return latestPreviousRow;
    }
    if (!latestPreviousRow) return currentRow;
    return getDateKey(currentRow.REPORT_DATE) > getDateKey(latestPreviousRow.REPORT_DATE)
      ? currentRow
      : latestPreviousRow;
  }, undefined);

  return (
    <article className={`${styles.overviewMetricCard} ${styles.productionResultCard}`}>
      <h3>생산 실적</h3>
      <div className={styles.productionResultValue}>
        <strong>{formatNumber(row?.RESULT_COUNT, 2)}</strong>
        <span>건</span>
        {previousRow && (
          <small data-direction={getDeltaDirection(row?.RESULT_COUNT, previousRow.RESULT_COUNT)}>
            전일대비 {formatDelta(row?.RESULT_COUNT, previousRow.RESULT_COUNT)}
          </small>
        )}
      </div>
      <p className={styles.productionResultDetails}>
        <span>
          지시 <strong>{formatNumber(row?.WORK_ORDER_COUNT, 2)}</strong>건
          {previousRow && (
            <small data-direction={getDeltaDirection(row?.WORK_ORDER_COUNT, previousRow.WORK_ORDER_COUNT)}>
              {formatDelta(row?.WORK_ORDER_COUNT, previousRow.WORK_ORDER_COUNT)}
            </small>
          )}
        </span>
        <i aria-hidden="true">·</i>
        <span>
          가동설비 <strong>{formatNumber(row?.ACTIVE_EQUIPMENT_COUNT, 2)}</strong>대
          {previousRow && (
            <small data-direction={getDeltaDirection(row?.ACTIVE_EQUIPMENT_COUNT, previousRow.ACTIVE_EQUIPMENT_COUNT)}>
              {formatDelta(row?.ACTIVE_EQUIPMENT_COUNT, previousRow.ACTIVE_EQUIPMENT_COUNT)}
            </small>
          )}
        </span>
      </p>
      <p className={styles.productionResultDetails}>
        <span>
          작업자 <strong>{formatNumber(row?.WORKER_COUNT, 2)}</strong>명
          {previousRow && (
            <small data-direction={getDeltaDirection(row?.WORKER_COUNT, previousRow.WORKER_COUNT)}>
              {formatDelta(row?.WORKER_COUNT, previousRow.WORKER_COUNT)}
            </small>
          )}
        </span>
        <i aria-hidden="true">·</i>
        <span>
          실적수량 <strong>{formatNumber(row?.RESULT_QTY, 2)}</strong> EA
          {previousRow && (
            <small data-direction={getDeltaDirection(row?.RESULT_QTY, previousRow.RESULT_QTY)}>
              {formatDelta(row?.RESULT_QTY, previousRow.RESULT_QTY)}
            </small>
          )}
        </span>
      </p>
    </article>
  );
}
