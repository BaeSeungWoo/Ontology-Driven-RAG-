import type { MesViewRow } from "@/services/mesApi";
import styles from "../../../mes.module.css";
import { toNumber } from "../../reportUtils";

function getDateKey(value: unknown): string {
  const dateValue = String(value ?? "").trim();
  return /^\d{4}-\d{2}-\d{2}/.test(dateValue) ? dateValue.slice(0, 10) : dateValue;
}

export default function EquipmentRate({ rows }: { rows: MesViewRow[] }) {
  const latestDate = rows.reduce(
    (latest, row) => {
      const date = getDateKey(row.BASE_DATE);
      return date > latest ? date : latest;
    },
    "",
  );
  const latestRows = rows.filter((row) => getDateKey(row.BASE_DATE) === latestDate);
  const operatingRates = latestRows
    .map((row) => toNumber(row.OPERATION_RATE))
    .filter((rate) => rate > 0);
  const averageRate = operatingRates.length > 0
    ? operatingRates.reduce((sum, rate) => sum + rate, 0) / operatingRates.length
    : 0;
  const highCount = operatingRates.filter((rate) => rate >= 70).length;
  const middleCount = operatingRates.filter((rate) => rate >= 30 && rate < 70).length;
  const lowCount = operatingRates.filter((rate) => rate < 30).length;
  const stoppedCount = latestRows.filter((row) => toNumber(row.OPERATION_RATE) === 0).length;

  return (
    <article className={`${styles.overviewMetricCard} ${styles.equipmentBiasCard}`}>
      <h3>설비 가동률</h3>
      <div className={styles.equipmentBiasValue}>
        <strong>{averageRate.toFixed(1)}</strong>
        <span>%</span>
      </div>
      <p
        className={styles.equipmentRateLegend}
        aria-label={`70% 이상 ${highCount}대, 30~69.9% ${middleCount}대, 30% 미만 ${lowCount}대, 정지 ${stoppedCount}대`}
      >
        <span><i data-tone="good" aria-hidden="true" />70% 이상 <strong>{highCount}</strong>대</span>
        <span><i data-tone="watch" aria-hidden="true" />30~69.9% <strong>{middleCount}</strong>대</span>
        <span><i data-tone="warn" aria-hidden="true" />30% 미만 <strong>{lowCount}</strong>대</span>
        <span><i data-tone="stop" aria-hidden="true" />정지 <strong>{stoppedCount}</strong>대</span>
      </p>
    </article>
  );
}
