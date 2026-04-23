"use client";

import { useMemo } from "react";
import type { MetricCardData, MetricCardOptions, ShipmentMetricsApi } from "@/types/dailyReport";
import styles from "../../checkpoint.module.css";
import MetricCardBase from "./metricCardBase";

type ShipmentCardProps = {
  options?: MetricCardOptions;
  apiData?: ShipmentMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "02 · Shipment",
  domainKo: "출하",
  badge: "WATCH",
  badgeTone: "watch",
  value: "-",
  unit: "EA 출하",
  sub1Label: "예정",
  sub1Value: "-",
  sub2Label: "미출",
  sub2Value: "-",
};

function mapShipmentToCard(apiData: ShipmentMetricsApi): Partial<MetricCardData> {
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const shipQty = apiData.shipQty ?? 0;
  const planQty = apiData.planQty ?? 0;
  const gapQty = planQty - shipQty;
  const rate = planQty > 0 ? (shipQty / planQty) * 100 : 0;
  const badgeInfo: Pick<MetricCardData, "badge" | "badgeTone"> =
    planQty === 0
      ? { badge: "GOOD", badgeTone: "good" }
      : rate < 30
        ? { badge: "WARN", badgeTone: "warn" }
        : rate < 70
          ? { badge: "WATCH", badgeTone: "watch" }
          : { badge: "GOOD", badgeTone: "good" };

  return {
    badge: badgeInfo.badge,
    badgeTone: badgeInfo.badgeTone,
    value: formatQty(shipQty),
    sub1Value: `${formatQty(planQty)} EA`,
    sub2Value: (
      <>
        <span className={gapQty > 0 ? styles.metricValueWarn : undefined}>{formatQty(gapQty)}</span> EA
      </>
    ),
  };
}

export default function ShipmentCard({ options, apiData, isLoading = false, errorMessage }: ShipmentCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapShipmentToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}
