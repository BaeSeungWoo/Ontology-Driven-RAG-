"use client";

import { useMemo } from "react";
import type { MetricCardData, MetricCardOptions, QualityMetricsApi } from "@/types/dailyReport";
import styles from "../../checkpoint.module.css";
import MetricCardBase from "./metricCardBase";

type QualityCardProps = {
  options?: MetricCardOptions;
  apiData?: QualityMetricsApi;
  isLoading?: boolean;
  errorMessage?: string;
};

const DEFAULT_DATA: MetricCardData = {
  domain: "04 · Quality",
  domainKo: "품질",
  badge: "WATCH",
  badgeTone: "watch",
  value: "-",
  unit: "% 불량률",
  sub1Label: "불량",
  sub1Value: "-",
  sub2Label: "PPM",
  sub2Value: "-",
};

function mapQualityToCard(apiData: QualityMetricsApi): Partial<MetricCardData> {
  const formatRate = (value: number) => (value === 0 ? "0" : value.toFixed(2));
  const formatQty = (value: number) => value.toLocaleString("ko-KR");
  const rate = apiData.defectRate ?? 0;
  const defectQty = apiData.defectQty ?? 0;
  const ppm = apiData.ppm ?? 0;
  const badgeInfo: Pick<MetricCardData, "badge" | "badgeTone"> =
    rate < 30
      ? { badge: "GOOD", badgeTone: "good" }
      : rate < 70
        ? { badge: "WATCH", badgeTone: "watch" }
        : { badge: "WARN", badgeTone: "warn" };

  return {
    badge: badgeInfo.badge,
    badgeTone: badgeInfo.badgeTone,
    value: formatRate(rate),
    sub1Value: (
      <>
        <span className={defectQty > 0 ? styles.metricValueWarn : undefined}>{formatQty(defectQty)}</span> EA
      </>
    ),
    sub2Value: formatQty(ppm),
  };
}

export default function QualityCard({ options, apiData, isLoading = false, errorMessage }: QualityCardProps) {
  const cardData = useMemo<MetricCardData>(() => {
    return {
      ...DEFAULT_DATA,
      ...(apiData ? mapQualityToCard(apiData) : {}),
      ...options,
    };
  }, [apiData, options]);

  return <MetricCardBase data={cardData} isLoading={isLoading} errorMessage={errorMessage} />;
}
