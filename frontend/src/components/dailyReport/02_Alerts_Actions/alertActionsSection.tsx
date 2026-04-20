import type { DailyAnomalyActionApi } from "@/types/dailyReport";
import styles from "../dailyReport.module.css";
import SectionHeading from "../sectionHeading";

type AlertActionsSectionProps = {
  anomalyAction?: DailyAnomalyActionApi;
  isLoading?: boolean;
};

export default function AlertActionsSection({
  anomalyAction,
  isLoading = false,
}: AlertActionsSectionProps) {
  const anomaly = anomalyAction?.anomaly ?? [];
  const action = anomalyAction?.action ?? [];

  return (
    <div>
      <SectionHeading idx="02 / 이상 징후 · Action Items" title="Alerts &" emphasize="Actions" />
      <div className={styles.dualGrid}>
        <article className={`${styles.alertCard} ${styles.alertWarn}`}>
          <p className={styles.alertLabel}>Anomaly Detection</p>
          <h3 className={styles.alertTitle}>이상 징후 및 경고</h3>
          <ul className={styles.alertList}>
            {isLoading && <li>로딩 중...</li>}
            {!isLoading && anomaly.length === 0 && <li>표시할 이상 징후가 없습니다.</li>}
            {!isLoading &&
              anomaly.map((item, index) => (
                <li key={`anomaly-${index}`}>
                  <span className={styles.marker}>•</span>
                  <span>{item}</span>
                </li>
              ))}
          </ul>
        </article>

        <article className={`${styles.alertCard} ${styles.alertAction}`}>
          <p className={styles.alertLabel}>Today&apos;s Priority</p>
          <h3 className={styles.alertTitle}>금일 우선 Action Items</h3>
          <ul className={styles.alertList}>
            {isLoading && <li>로딩 중...</li>}
            {!isLoading && action.length === 0 && <li>표시할 조치 항목이 없습니다.</li>}
            {!isLoading &&
              action.map((item, index) => (
                <li key={`action-${index}`}>
                  <span className={styles.marker}>•</span>
                  <span>{item}</span>
                </li>
              ))}
          </ul>
        </article>
      </div>
    </div>
  );
}
