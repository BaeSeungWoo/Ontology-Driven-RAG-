"use client";

import { useMemo } from "react";
import type { AttendanceMetricsApi, MetricCardData, MetricCardOptions } from "@/types/dailyReport";
import styles from "../../checkpoint.module.css";
import MetricCardBase from "./metricCardBase";

type AttendanceCardProps = {
  options?: MetricCardOptions;
  apiData?: AttendanceMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "06 · Attendance",
  domainKo: "근태",
  badge: "GOOD",
  badgeTone: "good",
  value: "-",
  unit: "/ 인원",
  sub1Label: "결근",
  sub1Value: "-",
  sub2Label: "잔업",
  sub2Value: "-",
};

function mapAttendanceToCard(apiData: AttendanceMetricsApi): Partial<MetricCardData> {
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const work = apiData.work ?? 0;
  const total = apiData.total ?? 0;
  const absence = apiData.absence ?? 0;
  const overtime = apiData.overtime ?? 0;
  const rate = total > 0 ? (work / total) * 100 : 0;
  const badgeInfo: Pick<MetricCardData, "badge" | "badgeTone"> =
    total === 0
      ? { badge: "GOOD", badgeTone: "good" }
      : rate < 30
        ? { badge: "WARN", badgeTone: "warn" }
        : rate < 70
          ? { badge: "WATCH", badgeTone: "watch" }
          : { badge: "GOOD", badgeTone: "good" };

  return {
    badge: badgeInfo.badge,
    badgeTone: badgeInfo.badgeTone,
    value: formatQty(work),
    sub1Value: (
      <>
        <span className={absence > 0 ? styles.metricValueWarn : undefined}>{formatQty(absence)}</span> 명
      </>
    ),
    sub2Value: (
      <>
        <span className={overtime > 0 ? styles.metricValueWatch : undefined}>{formatQty(overtime)}</span> 명
      </>
    ),
    unit: `/ ${formatQty(total)}명`,
  };
}

export default function AttendanceCard({ options, apiData, isLoading = false, errorMessage }: AttendanceCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapAttendanceToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}
