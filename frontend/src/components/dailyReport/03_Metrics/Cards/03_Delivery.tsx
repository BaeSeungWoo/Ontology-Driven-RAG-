"use client";

import { useMemo } from "react";
import type { DeliveryMetricsApi, MetricCardData, MetricCardOptions } from "@/types/dailyReport";
import styles from "../../dailyReport.module.css";
import MetricCardBase from "./metricCardBase";

type DeliveryCardProps = {
  options?: MetricCardOptions;
  apiData?: DeliveryMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "03 · Delivery",
  domainKo: "납기",
  badge: "GOOD",
  badgeTone: "good",
  value: "-",
  unit: "% 준수",
  sub1Label: "위험",
  sub1Value: "-",
  sub2Label: "지연",
  sub2Value: "-",
};

function mapDeliveryToCard(apiData: DeliveryMetricsApi): Partial<MetricCardData> {
  const formatRate = (value: number) => (value === 0 ? "0" : value.toFixed(2));
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const rate = apiData.delvRate ?? 0;
  const dangerCnt = apiData.dangerCnt ?? 0;
  const delayCnt = apiData.delayCnt ?? 0;
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
        <span className={dangerCnt > 0 ? styles.metricValueWarn : undefined}>{formatQty(dangerCnt)}</span> 건
      </>
    ),
    sub2Value: (
      <>
        <span className={delayCnt > 0 ? styles.metricValueWatch : undefined}>{formatQty(delayCnt)}</span> 건
      </>
    ),
  };
}

export default function DeliveryCard({ options, apiData, isLoading = false, errorMessage }: DeliveryCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapDeliveryToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}

