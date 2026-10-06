import CmsHourlyChart from "./cmsHourlyChart";
import type { CmsReport } from "@/services/cmsApi";
import { evaluateDelta, formatDelta, formatHours } from "../cmsReportFormatting";
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
  const previousChartPoint = chartPoints.at(-2);
  const weeklyDelta = latestChartPoint && previousChartPoint ? latestChartPoint.value - previousChartPoint.value : null;
  const highest = chartPoints.reduce<(typeof chartPoints)[number] | undefined>((best, point) => !best || point.value > best.value ? point : best, undefined);
  const lowest = chartPoints.reduce<(typeof chartPoints)[number] | undefined>((best, point) => !best || point.value < best.value ? point : best, undefined);
  const totalMinutes = Math.round(totalStatusSeconds / 60);

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
        {latestChartPoint && (
          <div className={styles.weeklyHeadline}>
            <strong>{latestChartPoint.value.toFixed(1)}%</strong>
            <span>{latestChartPoint.label} 기준</span>
            <span className={`${styles.weeklyDelta} ${styles[`delta_${evaluateDelta(weeklyDelta, true)}`]}`}>
              {weeklyDelta === null ? "전일 데이터 없음" : `전일 대비 ${formatDelta(weeklyDelta, "point")}`}
            </span>
          </div>
        )}
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
            {chartPoints.map(point => (
              <line key={`guide-${point.workDate}`} x1={point.x} x2={point.x} y1={chartPadding.top} y2={chartBaseline} className={styles.chartGuide} />
            ))}
            <polygon points={chartArea} className={styles.chartArea} />
            <polyline points={chartLine} className={styles.chartLine} />
            {chartPoints.map((point) => (
              <g key={point.workDate}>
                <title>{`${point.workDate}: ${point.value.toFixed(2)}%`}</title>
                {point === latestChartPoint && <circle cx={point.x} cy={point.y} r={11} className={styles.chartLatestBand} />}
                <circle cx={point.x} cy={point.y} r={point.workDate === latestChartPoint?.workDate ? "6" : "5"} className={`${styles.chartPoint} ${point.workDate === latestChartPoint?.workDate ? styles.chartPointLatest : ""}`} />
                <text x={point.x} y={point.y < chartPadding.top + 22 ? point.y + 20 : point.y - 14} className={`${styles.chartValue} ${point.workDate === latestChartPoint?.workDate ? styles.chartValueLatest : ""}`} textAnchor="middle">{point.value.toFixed(1)}%</text>
                <text x={point.x} y={chartBaseline + 24} className={`${styles.chartDate} ${point.workDate === latestChartPoint?.workDate ? styles.chartDateLatest : ""}`} textAnchor="middle">{point.label}</text>
              </g>
            ))}
          </svg>
        </div>
        {highest && lowest && (
          <div className={styles.weeklyExtremes}>
            <div><span>7일 최고</span><strong>{highest.value.toFixed(1)}%</strong><small> · {highest.label}</small></div>
            <div><span>7일 최저</span><strong>{lowest.value.toFixed(1)}%</strong><small> · {lowest.label}</small></div>
          </div>
        )}
      </article>

      <article className={`${styles.reportPanel} ${styles.statusReportPanel}`}>
        <div className={styles.chartHeader}>
          <div><p className={styles.sectionLabel}>Equipment status</p><h3>가동현황</h3></div>
          <span>단위: 시간</span>
        </div>
        <p className={styles.statusCaption}>상태별 누적 시간</p>
        <div className={styles.statusOverview}>
          <div className={styles.statusDonutWrap}>
            <svg viewBox="0 0 200 200" role="img" aria-label="설비 상태별 시간 비율">
              {statusSegments.map((segment) => (
                <circle key={segment.label} cx="100" cy="100" r="72" className={styles.statusDonutSegment} pathLength="1" stroke={segment.color} strokeDasharray={`${Math.max(segment.ratio - 0.007, 0)} ${1 - Math.max(segment.ratio - 0.007, 0)}`} strokeDashoffset={-segment.offset} transform="rotate(-90 100 100)">
                  <title>{`${segment.label}: ${(segment.ratio * 100).toFixed(1)}%, ${formatHours(segment.seconds)}`}</title>
                </circle>
              ))}
              {statusSegments.filter(segment => segment.ratio > 0).map(segment => {
                const angle = (segment.offset + segment.ratio / 2) * Math.PI * 2 - Math.PI / 2;
                return (
                  <text key={`${segment.label}-share`} x={100 + Math.cos(angle) * 72} y={100 + Math.sin(angle) * 72}
                    textAnchor="middle" dominantBaseline="central" className={styles.statusSegmentShare}
                    fill="#fff">
                    {(segment.ratio * 100).toFixed(1)}%
                  </text>
                );
              })}
              <text x="100" y="85" className={styles.statusDonutLabel} textAnchor="middle">총 집계 시간</text>
              <text x="100" y="108" className={styles.statusDonutTotal} textAnchor="middle">{Math.floor(totalMinutes / 60).toLocaleString("ko-KR")}시간</text>
              <text x="100" y="127" className={styles.statusDonutLabel} textAnchor="middle">{totalMinutes % 60}분</text>
            </svg>
          </div>
          <table className={styles.statusTable} aria-label="상태별 누적 시간과 비중">
            <thead><tr><th scope="col">상태</th><th scope="col">누적 시간</th><th scope="col">비중</th></tr></thead>
            <tbody>{statusSegments.map((segment) => (
              <tr key={segment.label}>
                <th scope="row"><span><i style={{ backgroundColor: segment.color }} />{segment.label}</span></th>
                <td>{formatHours(segment.seconds)}</td>
                <td><b style={{ backgroundColor: `${segment.color}18`, color: segment.label === "전원 OFF" ? "#586977" : segment.label === "정지" ? "#946000" : segment.color }}>{(segment.ratio * 100).toFixed(1)}%</b></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <p className={styles.statusFootnote}>비중은 상태별 집계 시간의 합계를 기준으로 계산합니다.</p>
      </article>

      <article className={`${styles.reportPanel} ${styles.hourlyReportPanel}`}>
        <p className={styles.sectionLabel}>Hourly operation rate</p>
        <h3>시간대별 가동률</h3>
        <CmsHourlyChart report={report} />
      </article>
    </section>
  );
}
