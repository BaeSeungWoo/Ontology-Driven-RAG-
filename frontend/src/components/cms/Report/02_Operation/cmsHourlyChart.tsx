import { ArrowDown, ChartNoAxesColumnIncreasing, Clock3 } from "lucide-react";
import type { CmsReport } from "@/services/cmsApi";
import styles from "../../cms.module.css";

export default function CmsHourlyChart({ report }: { report: CmsReport }) {
  const rates = report.hourlyRates;
  if (!rates.length) return <p className={styles.message}>시간대별 가동률 데이터가 없습니다.</p>;

  const highest = rates.reduce((a, b) => b.value > a.value ? b : a);
  const lowest = rates.reduce((a, b) => b.value < a.value ? b : a);
  const lowRates = rates.filter(rate => rate.value < 30);
  const midnight = rates.findIndex((rate, index) => index > 0 && rate.label === "00:00");
  const workDate = report.weeklyPlannedRates.at(-1)?.workDate;
  const nextDate = workDate ? new Date(`${workDate}T00:00:00Z`) : null;
  nextDate?.setUTCDate(nextDate.getUTCDate() + 1);
  const dateLabel = (date: string) => `${Number(date.slice(5, 7))}월 ${Number(date.slice(8, 10))}일`;
  const width = 1100;
  const left = 48;
  const right = width - 20;
  const top = 28;
  const baseline = 244;
  const step = (right - left) / rates.length;
  const y = (value: number) => baseline - (baseline - top) * value / 100;

  return (
    <>
      <div className={styles.hourlyHighlights}>
        <div><ChartNoAxesColumnIncreasing aria-hidden="true" /><span>최고 가동률<strong>{highest.value.toFixed(1)}% <small>· {highest.label}</small></strong></span></div>
        <div><ArrowDown aria-hidden="true" /><span>최저 가동률<strong>{lowest.value.toFixed(1)}% <small>· {lowest.label}</small></strong></span></div>
        <div><Clock3 aria-hidden="true" /><span>30% 미만<strong>{lowRates.length}개 시간대{lowRates.length > 0 && <small> · {lowRates.map(rate => rate.label).join(", ")}</small>}</strong></span></div>
      </div>
      <div className={styles.hourlyChartScroll} tabIndex={0} role="region" aria-label="시간대별 가동률 차트, 좁은 화면에서는 가로로 스크롤하세요">
        <svg className={styles.hourlyChart} viewBox={`0 0 ${width} 310`} role="group" aria-label="시간대별 가동률, 세로축 0~100%">
          {[0, 25, 50, 75, 100].map(value => (
            <g key={value}>
              <line x1={left} x2={right} y1={y(value)} y2={y(value)} className={styles.chartGuide} />
              <text x={left - 10} y={y(value) + 4} textAnchor="end" className={styles.chartLabel}>{value}%</text>
            </g>
          ))}
          {midnight > 0 && <line x1={left + midnight * step} x2={left + midnight * step} y1={top} y2={baseline} className={styles.chartGuide} />}
          {rates.map((rate, index) => {
            const center = left + step * (index + 0.5);
            const low = rate.value < 30;
            return (
              <g key={rate.label}>
                <rect x={center - step * 0.3} y={y(rate.value)} width={step * 0.6} height={baseline - y(rate.value)} rx={3}
                  className={low ? styles.hourlyBarLow : styles.hourlyBar} tabIndex={0} role="img" aria-label={`${rate.label} 가동률 ${rate.value.toFixed(1)}%`}>
                  <title>{rate.label} · {rate.value.toFixed(1)}%</title>
                </rect>
                <text x={center} y={baseline + 22} textAnchor="middle" className={styles.chartDate}>{rate.label.slice(0, 2)}</text>
              </g>
            );
          })}
          <line x1={left} x2={right} y1={y(30)} y2={y(30)} className={styles.hourlyThreshold} />
          {rates.map((rate, index) => {
            if (rate !== highest && rate !== lowest) return null;
            const center = left + step * (index + 0.5);
            const labelWidth = Math.min(52, step - 4);
            return (
              <g key={`value-${rate.label}`} className={styles.hourlyValueLabel}>
                <rect x={center - labelWidth / 2} y={y(rate.value) - 24} width={labelWidth} height={20} rx={4} />
                <text x={center} y={y(rate.value) - 10} textAnchor="middle" className={rate.value < 30 ? styles.hourlyLowValue : styles.chartValue}>{rate.value.toFixed(1)}%</text>
              </g>
            );
          })}
          {workDate && <text x={left} y={296} className={styles.chartDate}>{dateLabel(workDate)}</text>}
          {midnight > 0 && nextDate && <text x={left + midnight * step + 8} y={296} className={styles.chartDate}>{dateLabel(nextDate.toISOString().slice(0, 10))}</text>}
        </svg>
      </div>
      <div className={styles.hourlyLegend}><span><i />가동률</span><span><i />30% 미만</span><span><i className={styles.hourlyThresholdKey} />저가동 기준 30%</span></div>
    </>
  );
}
