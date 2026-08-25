import type { CmsReport } from "@/services/cmsApi";
import { evaluateDelta, formatDelta, formatHours, formatRate } from "../cmsReportFormatting";
import styles from "../../cms.module.css";

export default function CmsReportMetrics({ report }: { report: CmsReport }) {
  const previousTotals = report.dailyTotals.at(-2);
  const previousPlannedRate = report.weeklyPlannedRates.at(-2)?.value ?? null;
  const metrics = [
    {
      label: "계획가동률",
      value: formatRate(report.metrics.plannedRate),
      delta: report.metrics.plannedRate === null || previousPlannedRate === null
        ? null
        : report.metrics.plannedRate - previousPlannedRate,
      unit: "point" as const,
      isIncreaseGood: true,
    },
    {
      label: "실제 가동시간",
      value: formatHours(report.metrics.operateSeconds),
      delta: previousTotals ? (report.metrics.operateSeconds - previousTotals.operateSeconds) / 3600 : null,
      unit: "hours" as const,
      isIncreaseGood: true,
    },
    {
      label: "알람시간",
      value: formatHours(report.metrics.alarmSeconds),
      delta: previousTotals ? (report.metrics.alarmSeconds - previousTotals.alarmSeconds) / 3600 : null,
      unit: "hours" as const,
      isIncreaseGood: false,
    },
    {
      label: "정지시간",
      value: formatHours(report.metrics.stopSeconds),
      delta: previousTotals ? (report.metrics.stopSeconds - previousTotals.stopSeconds) / 3600 : null,
      unit: "hours" as const,
      isIncreaseGood: false,
    },
    {
      label: "전원 OFF 시간",
      value: formatHours(report.metrics.offSeconds),
      delta: previousTotals ? (report.metrics.offSeconds - previousTotals.offSeconds) / 3600 : null,
      unit: "hours" as const,
      isIncreaseGood: false,
    },
  ];

  return (
    <section>
      <p className={styles.sectionLabel}>Day-over-day change</p>
      <div className={styles.metricsHeading}>
        <h3>전일 대비 변화</h3>
        <span>당일 계획공수 {formatHours(report.metrics.plannedSeconds)}</span>
      </div>
      <div className={styles.kpiGrid}>
        {metrics.map((metric) => (
          <article key={metric.label} className={styles.kpiCard}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
            <b className={styles[`delta_${evaluateDelta(metric.delta, metric.isIncreaseGood)}`]}>
              {formatDelta(metric.delta, metric.unit)}
            </b>
          </article>
        ))}
      </div>
    </section>
  );
}
