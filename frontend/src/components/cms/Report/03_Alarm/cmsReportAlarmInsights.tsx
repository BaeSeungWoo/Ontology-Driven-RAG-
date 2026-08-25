import type { CmsReport } from "@/services/cmsApi";
import { formatDateTime, formatDuration } from "../cmsReportFormatting";
import styles from "../../cms.module.css";

export default function CmsReportAlarmInsights({ report }: { report: CmsReport }) {
  return (
    <section className={styles.alarmInsightGrid}>
      <article className={styles.alarmInsightPanel}>
        <p className={styles.sectionLabel}>Alarm by machine</p>
        <h3>최다 알람 발생 장비 Top 3</h3>
        {report.topAlarmMachines.length > 0 ? (
          <ol className={styles.alarmInsightList}>
            {report.topAlarmMachines.map((machine) => (
              <li key={machine.machineCode} className={machine.rank === 1 ? styles.alarmInsightTopRank : undefined}><span>{String(machine.rank).padStart(2, "0")}</span><div><strong>{machine.machineName}</strong><small>{machine.machineCode}</small></div><b>{machine.count}건</b></li>
            ))}
          </ol>
        ) : <p className={styles.emptyAlarmInsight}>장비별 알람 데이터가 없습니다.</p>}
      </article>
      <article className={styles.alarmInsightPanel}>
        <p className={styles.sectionLabel}>Longest alarm events</p>
        <h3>최장 알람 이력 Top 3</h3>
        {report.longestAlarms.length > 0 ? (
          <ol className={styles.alarmInsightList}>
            {report.longestAlarms.map((alarm) => (
              <li key={`${alarm.rank}-${alarm.machineCode}-${alarm.occurDate}`} className={alarm.rank === 1 ? styles.alarmInsightTopRank : undefined}><span>{String(alarm.rank).padStart(2, "0")}</span><div><strong>{alarm.machineName} · {alarm.code}</strong><small>{alarm.details}</small><small>{formatDateTime(alarm.occurDate)} ~ {formatDateTime(alarm.finishDate)}</small></div><b>{formatDuration(alarm.durationSeconds)}</b></li>
            ))}
          </ol>
        ) : <p className={styles.emptyAlarmInsight}>지속시간이 있는 알람 이력이 없습니다.</p>}
      </article>
    </section>
  );
}
