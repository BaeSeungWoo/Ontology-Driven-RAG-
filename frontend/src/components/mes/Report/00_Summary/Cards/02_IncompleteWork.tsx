import type { MesViewRow } from "@/services/mesApi";
import styles from "../../../mes.module.css";
import { formatNumber } from "../../reportUtils";

function formatProcess(value: unknown, fallback: string): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

export default function IncompleteWork({ rows }: { rows: MesViewRow[] }) {
  const row = rows[0];
  const processName = formatProcess(row?.TOP_PROCESS_NAME, "미등록 공정");
  const processSequence = formatProcess(row?.TOP_PROCESS_SEQ, "-");

  return (
    <article className={`${styles.overviewMetricCard} ${styles.incompleteWorkCard}`}>
      <h3>미완료 작업</h3>
      <div className={styles.incompleteWorkValue}>
        <strong>{formatNumber(row?.INCOMPLETE_COUNT, 2)}</strong>
        <span>건</span>
      </div>
      <p className={styles.incompleteWorkDetails}>
        <span>미착수 <strong>{formatNumber(row?.NOT_STARTED_COUNT, 2)}</strong>건</span>
        <i aria-hidden="true">·</i>
        <span>진행 중 <strong>{formatNumber(row?.IN_PROGRESS_COUNT, 2)}</strong>건</span>
      </p>
      <p className={styles.incompleteWorkDetails}>
        <span>
          최다 공정 <strong>({processName}, {processSequence})</strong>
          {" - "}<strong>{formatNumber(row?.TOP_PROCESS_COUNT, 2)}</strong>건
        </span>
      </p>
    </article>
  );
}
