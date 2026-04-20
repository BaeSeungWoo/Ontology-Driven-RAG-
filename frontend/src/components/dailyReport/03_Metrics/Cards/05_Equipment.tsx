"use client";

import { useMemo } from "react";
import type { EquipmentMetricsApi, MetricCardData, MetricCardOptions } from "@/types/dailyReport";
import styles from "../../dailyReport.module.css";
import MetricCardBase from "./metricCardBase";

type EquipmentCardProps = {
  options?: MetricCardOptions;
  apiData?: EquipmentMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "05 · Equipment",
  domainKo: "설비 (CNC)",
  badge: "WATCH",
  badgeTone: "watch",
  value: "-",
  unit: "% 가동률",
  sub1Label: "고장",
  sub1Value: "-",
  sub2Label: "알람",
  sub2Value: "-",
};

function mapEquipmentToCard(apiData: EquipmentMetricsApi): Partial<MetricCardData> {
  const formatRate = (value: number) => (value === 0 ? "0" : value.toFixed(2));
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const rate = apiData.runningRate ?? 0;
  const alarmEquipQty = apiData.alarmEquipQty ?? 0;
  const alarmCnt = apiData.alarmCnt ?? 0;
  const badgeInfo: Pick<MetricCardData, "badge" | "badgeTone"> =
    rate < 30
      ? { badge: "WARN", badgeTone: "warn" }
      : rate < 70
        ? { badge: "WATCH", badgeTone: "watch" }
        : { badge: "GOOD", badgeTone: "good" };

  return {
    badge: badgeInfo.badge,
    badgeTone: badgeInfo.badgeTone,
    value: formatRate(rate),
    sub1Value: (
      <>
        <span className={alarmEquipQty > 0 ? styles.metricValueWarn : undefined}>{formatQty(alarmEquipQty)}</span> 대
      </>
    ),
    sub2Value: (
      <>
        <span className={alarmCnt > 0 ? styles.metricValueWatch : undefined}>{formatQty(alarmCnt)}</span> 건
      </>
    ),
  };
}

export default function EquipmentCard({ options, apiData, isLoading = false, errorMessage }: EquipmentCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapEquipmentToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}
