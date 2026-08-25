import type { CmsReport } from "@/services/cmsApi";
import { evaluateRate, formatHours } from "../cmsReportFormatting";
import styles from "../../cms.module.css";

export default function CmsReportOperations({ report }: { report: CmsReport }) {
  const statusItems = [
    { label: "가동", seconds: report.metrics.operateSeconds, color: "#1f9b5a" },
    { label: "정지", seconds: report.metrics.stopSeconds, color: "#d68a00" },
    { label: "알람", seconds: report.metrics.alarmSeconds, color: "#d6453d" },
    { label: "전원 OFF", seconds: report.metrics.offSeconds, color: "#b9c4c1" },
  ];
  const totalStatusSeconds = statusItems.reduce((total, item) => total + item.seconds, 0);
  let accumulatedRatio = 0;
  const statusSegments = statusItems.map((item) => {
    const ratio = totalStatusSeconds > 0 ? item.seconds / totalStatusSeconds : 0;
    const segment = { ...item, ratio, offset: accumulatedRatio };
    accumulatedRatio += ratio;
    return segment;
  });
  const chartWidth = 700;
  const chartHeight = 240;
  const chartPadding = { top: 30, right: 24, bottom: 42, left: 42 };
  const chartInnerWidth = chartWidth - chartPadding.left - chartPadding.right;
  const chartInnerHeight = chartHeight - chartPadding.top - chartPadding.bottom;
  const chartMaxRate = Math.max(
    50,
    Math.ceil(Math.max(...report.weeklyPlannedRates.map((rate) => rate.value)) / 10) * 10,
  );
  const chartGuideRates = [0, chartMaxRate / 2, chartMaxRate];
  const chartPoints = report.weeklyPlannedRates.map((rate, index) => {
    const x = chartPadding.left + (chartInnerWidth * index) / Math.max(report.weeklyPlannedRates.length - 1, 1);
    const y = chartPadding.top + chartInnerHeight * (1 - rate.value / chartMaxRate);
    return { ...rate, x, y };
  });
  const chartLine = chartPoints.map((point) => `${point.x},${point.y}`).join(" ");
  const chartBaseline = chartPadding.top + chartInnerHeight;
  const chartArea = chartPoints.length > 0
    ? `${chartPoints[0].x},${chartBaseline} ${chartLine} ${chartPoints[chartPoints.length - 1].x},${chartBaseline}`
    : "";
  const latestChartPoint = chartPoints.at(-1);
  const hourlyRateColumns = [report.hourlyRates.slice(0, 12), report.hourlyRates.slice(12, 24)];

  return (
    <section className={styles.reportGrid}>
      <article className={`${styles.reportPanel} ${styles.weeklyReportPanel}`}>
        <div className={styles.chartHeader}>
          <div>
            <p className={styles.sectionLabel}>Weekly planned rate</p>
            <h3>최근 7일 계획가동률 추이</h3>
          </div>
          <span>단위: %</span>
        </div>
        <div className={styles.lineChartWrap}>
          <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label="최근 7일 계획가동률 추이">
            {chartGuideRates.map((value) => {
              const y = chartPadding.top + chartInnerHeight * (1 - value / chartMaxRate);
              return (
                <g key={value}>
                  <line x1={chartPadding.left} x2={chartWidth - chartPadding.right} y1={y} y2={y} className={styles.chartGuide} />
                  <text x={chartPadding.left - 12} y={y + 4} className={styles.chartLabel} textAnchor="end">{value.toFixed(0)}</text>
                </g>
              );
            })}
            <polygon points={chartArea} className={styles.chartArea} />
            <polyline points={chartLine} className={styles.chartLine} />
            {chartPoints.map((point) => (
              <g key={point.workDate}>
                <title>{`${point.workDate}: ${point.value.toFixed(2)}%`}</title>
                <circle cx={point.x} cy={point.y} r={point.workDate === latestChartPoint?.workDate ? "6" : "5"} className={`${styles.chartPoint} ${point.workDate === latestChartPoint?.workDate ? styles.chartPointLatest : ""}`} />
                <text x={point.x} y={point.y < chartPadding.top + 22 ? point.y + 20 : point.y - 14} className={`${styles.chartValue} ${point.workDate === latestChartPoint?.workDate ? styles.chartValueLatest : ""}`} textAnchor="middle">{point.value.toFixed(1)}%</text>
                <text x={point.x} y={chartBaseline + 24} className={`${styles.chartDate} ${point.workDate === latestChartPoint?.workDate ? styles.chartDateLatest : ""}`} textAnchor="middle">{point.label}</text>
              </g>
            ))}
          </svg>
        </div>
      </article>

      <article className={`${styles.reportPanel} ${styles.statusReportPanel}`}>
        <div className={styles.chartHeader}>
          <div><p className={styles.sectionLabel}>Equipment status</p><h3>가동현황</h3></div>
          <span>단위: 시간</span>
        </div>
        <div className={styles.statusOverview}>
          <div className={styles.statusDonutWrap}>
            <svg viewBox="0 0 200 200" role="img" aria-label="설비 상태별 시간 비율">
              {statusSegments.map((segment) => (
                <circle key={segment.label} cx="100" cy="100" r="72" className={styles.statusDonutSegment} pathLength="1" stroke={segment.color} strokeDasharray={`${Math.max(segment.ratio - 0.007, 0)} ${1 - Math.max(segment.ratio - 0.007, 0)}`} strokeDashoffset={-segment.offset} transform="rotate(-90 100 100)">
                  <title>{`${segment.label}: ${(segment.ratio * 100).toFixed(1)}%, ${formatHours(segment.seconds)}`}</title>
                </circle>
              ))}
              <text x="100" y="94" className={styles.statusDonutLabel} textAnchor="middle">합계</text>
              <text x="100" y="116" className={styles.statusDonutTotal} textAnchor="middle">{formatHours(totalStatusSeconds)}</text>
            </svg>
          </div>
          <div className={styles.statusLegend}>
            {statusSegments.map((segment) => (
              <div key={segment.label}><span><i style={{ backgroundColor: segment.color }} />{segment.label}</span><strong>{formatHours(segment.seconds)} ({(segment.ratio * 100).toFixed(1)}%)</strong></div>
            ))}
          </div>
        </div>
      </article>

      <article className={`${styles.reportPanel} ${styles.hourlyReportPanel}`}>
        <p className={styles.sectionLabel}>Hourly operation rate</p>
        <h3>시간대별 가동률</h3>
        <div className={styles.hourlyRates}>
          {hourlyRateColumns.map((rates, columnIndex) => (
            <div key={columnIndex} className={styles.hourlyRateColumn}>
              {rates.map((rate) => (
                <div key={rate.label} className={styles.rateRow}>
                  <span>{rate.label}</span><div><i className={styles[`rate_${evaluateRate(rate.value)}`]} style={{ width: `${rate.value}%` }} /></div><b>{rate.value.toFixed(1)}%</b>
                </div>
              ))}
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
