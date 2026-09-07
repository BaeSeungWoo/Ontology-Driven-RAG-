import type { MesViewRow } from "@/services/mesApi";
import styles from "../../../mes.module.css";
import { formatNumber, toNumber } from "../../reportUtils";

export default function Inspection({ rows }: { rows: MesViewRow[] }) {
  const row = rows[0];
  const inspectionQuantity = toNumber(row?.ACCEPT_QTY) + toNumber(row?.DEFECT_QTY);

  return (
    <article className={`${styles.overviewMetricCard} ${styles.inspectionCard}`}>
      <h3>검사 실시</h3>
      <div className={styles.inspectionValue}>
        <strong>{formatNumber(row?.INSPECTION_COUNT)}</strong>
        <span>건</span>
      </div>
      <p className={styles.inspectionDetails}>
        <span>검사수량 <strong>{formatNumber(inspectionQuantity, 2)}</strong> EA</span>
        <i aria-hidden="true">·</i>
        <span>불량수량 <strong>{formatNumber(row?.DEFECT_QTY, 2)}</strong> EA</span>
      </p>
      <p className={styles.inspectionNote}>최근 7일 검사 데이터</p>
    </article>
  );
}
