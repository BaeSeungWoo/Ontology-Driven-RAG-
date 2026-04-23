import styles from "../../checkpoint.module.css";
import type { MetricCardData } from "@/types/dailyReport";

type MetricCardBaseProps = {
  data: MetricCardData;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function MetricCardBase({
  data,
  isLoading = false,
  errorMessage,
}: MetricCardBaseProps) {
  const hasError = Boolean(errorMessage);

  return (
    <article className={styles.metricCard}>
      <div className={styles.metricHead}>
        <p className={styles.metricDomain}>
          {data.domain}
          <span>{data.domainKo}</span>
        </p>
        <span
          className={`${styles.metricBadge} ${
            data.badgeTone === "good"
              ? styles.badgeGood
              : data.badgeTone === "warn"
                ? styles.badgeWarn
                : styles.badgeWatch
          }`}
        >
          {data.badge}
        </span>
      </div>

      <div className={styles.metricMain}>
        <strong
          className={
            data.badgeTone === "good"
              ? styles.metricMainValueGood
              : data.badgeTone === "warn"
                ? styles.metricMainValueWarn
                : styles.metricMainValueWatch
          }
        >
          {isLoading ? "..." : data.value}
        </strong>
        <span>{data.unit}</span>
      </div>

      <div className={styles.metricSub}>
        <div className={styles.metricSubItem}>
          <span>{data.sub1Label}</span>
          <span>{data.sub1Value}</span>
        </div>
        <div className={styles.metricSubItem}>
          <span>{data.sub2Label}</span>
          <span>{data.sub2Value}</span>
        </div>
      </div>

      {hasError && <p className={styles.metricsDebugError}>{errorMessage}</p>}
    </article>
  );
}
