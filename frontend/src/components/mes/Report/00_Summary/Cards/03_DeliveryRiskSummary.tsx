import type { MesViewRow } from "@/services/mesApi";
import styles from "../../../mes.module.css";
import { formatNumber } from "../../reportUtils";

export default function DeliveryRiskSummary({ rows }: { rows: MesViewRow[] }) {
  const row = rows[0];

  return (
    <article className={`${styles.overviewMetricCard} ${styles.deliveryRiskSummaryCard}`}>
      <h3>납기 임박(7일 이내)</h3>
      <div className={styles.deliveryRiskSummaryValue}>
        <strong>{formatNumber(row?.DUE_WITHIN_7_COUNT)}</strong>
        <span>건</span>
      </div>
      <p className={styles.deliveryRiskSummaryDetails}>
        <span>납기 경과(최대 30일) <strong>{formatNumber(row?.OVERDUE_COUNT)}</strong>건</span>
      </p>
      <p className={styles.deliveryRiskSummaryNote}>공정 미완료 수주 기준</p>
    </article>
  );
}
