"use client";

import { useMemo } from "react";
import type { MetricCardData, MetricCardOptions, ProductMetricsApi } from "@/types/dailyReport";
import styles from "../../checkpoint.module.css";
import MetricCardBase from "./metricCardBase";

type ProductionCardProps = {
  options?: MetricCardOptions;
  apiData?: ProductMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "01 · Production",
  domainKo: "생산",
  badge: "WARN",
  badgeTone: "warn",
  value: "-",
  unit: "% 달성",
  sub1Label: "계획",
  sub1Value: "-",
  sub2Label: "실적",
  sub2Value: "-",
};

function mapProductToCard(apiData: ProductMetricsApi): Partial<MetricCardData> {
  const formatRate = (value: number) => (value === 0 ? "0" : value.toFixed(2));
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const planQty = apiData.planQty ?? 0;
  const qty = apiData.qty ?? 0;
  const rate = planQty > 0 ? (qty / planQty) * 100 : 0;

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
    sub1Value: `${formatQty(planQty)} EA`,
    sub2Value: (
      <>
        <span
          className={
            qty === 0
              ? undefined
              : rate < 30
                ? styles.metricValueWarn
                : rate < 70
                  ? styles.metricValueWatch
                  : styles.metricMainValueGood
          }
        >
          {formatQty(qty)}
        </span>{" "}
        EA
      </>
    ),
  };
}

export default function ProductionCard({ options, apiData, isLoading = false, errorMessage }: ProductionCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapProductToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}

