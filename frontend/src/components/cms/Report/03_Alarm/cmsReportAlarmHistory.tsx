import type { CmsReport } from "@/services/cmsApi";
import styles from "../../cms.module.css";

export default function CmsReportAlarmHistory({ report }: { report: CmsReport }) {
  const primaryAlarms = report.topAlarms.slice(0, 3);
  const remainingAlarms = report.topAlarms.slice(3, 10);
  const paretoTotal = Math.max(
    report.metrics.alarmEvents,
    report.topAlarms.reduce((total, alarm) => total + alarm.count, 0),
  );
  const paretoAlarms = [...report.topAlarms]
    .sort((left, right) => right.count - left.count)
    .slice(0, 5)
    .map((alarm) => ({ ...alarm, share: paretoTotal > 0 ? (alarm.count / paretoTotal) * 100 : 0 }));

  return (
    <section className={styles.attentionPanel}>
      <div>
        <p className={styles.sectionLabel}>Alarm history</p>
        <h3>알람히스토리 요약</h3>
        <p className={styles.alarmTotal}>총 {report.metrics.alarmEvents}건 · {report.metrics.alarmTypes}종류</p>
        {primaryAlarms[0] && (
          <article className={styles.topAlarmFeature}>
            <span>01</span><strong>{primaryAlarms[0].code}</strong><b>발생 {primaryAlarms[0].count}건</b>
            <small>{primaryAlarms[0].machines.length > 0 ? `관련 설비 ${primaryAlarms[0].machines.join(", ")}` : "관련 설비 정보 없음"}</small>
          </article>
        )}
      </div>
      <div className={styles.issueList}>
        {report.topAlarms.length > 0 ? (
          <>
            <div className={styles.primaryAlarmList}>
              {primaryAlarms.slice(1).map((alarm, index) => (
                <article key={`${alarm.code}-${index}`}>
                  <span>{String(index + 2).padStart(2, "0")}</span>
                  <div><strong>{alarm.code}</strong><p>발생 {alarm.count}건</p><small>{alarm.machines.length > 0 ? `관련 설비 ${alarm.machines.join(", ")}` : "관련 설비 정보 없음"}</small></div>
                </article>
              ))}
            </div>
            {remainingAlarms.length > 0 && (
              <div className={styles.compactAlarmList}>
                {remainingAlarms.map((alarm, index) => (
                  <div key={`${alarm.code}-${index}`}><span>{String(index + 4).padStart(2, "0")}</span><strong>{alarm.code}</strong><b>{alarm.count}건</b></div>
                ))}
              </div>
            )}
          </>
        ) : <p>알람 요약 데이터가 없습니다.</p>}
      </div>
      <div className={styles.paretoPanel}>
        <p className={styles.sectionLabel}>Alarm pareto</p>
        <h3>알람 파레토</h3>
        <p>상위 5개 알람 · 총 {paretoTotal}건 기준</p>
        {paretoAlarms.length > 0 ? (
          <ol className={styles.paretoList}>
            {paretoAlarms.map((alarm, index) => (
              <li key={`${alarm.code}-${index}`}>
                <div><strong>{alarm.code}</strong><span>{alarm.count}건 · {alarm.share.toFixed(1)}%</span></div>
                <div className={styles.paretoBar}><i style={{ width: `${alarm.share}%` }} /></div>
              </li>
            ))}
          </ol>
        ) : <p>알람 파레토 데이터가 없습니다.</p>}
      </div>
    </section>
  );
}
