"use client";

import type { MetricCardOptions, MetricsAllApi } from "@/types/dailyReport";
import styles from "../dailyReport.module.css";
import SectionHeading from "../sectionHeading";
import AttendanceCard from "./Cards/06_Attendance";
import DeliveryCard from "./Cards/03_Delivery";
import EquipmentCard from "./Cards/05_Equipment";
import ProductionCard from "./Cards/01_Production";
import QualityCard from "./Cards/04_Quality";
import ShipmentCard from "./Cards/02_Shipment";

const CARD_OPTIONS: Record<string, MetricCardOptions> = {
  production: {},
  shipment: {},
  delivery: {},
  quality: {},
  equipment: {},
  attendance: {},
};

type MetricsSectionProps = {
  metrics?: MetricsAllApi;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function MetricsSection({
  metrics,
  isLoading = false,
  errorMessage = "",
}: MetricsSectionProps) {
  return (
    <div>
      <SectionHeading idx="03 / 핵심 지표 · 6 Domains" title="Key" emphasize="Metrics" />

      <div className={styles.metricsGrid}>
        <ProductionCard
          options={CARD_OPTIONS.production}
          apiData={metrics?.product}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
        <ShipmentCard
          options={CARD_OPTIONS.shipment}
          apiData={metrics?.shipment}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
        <DeliveryCard
          options={CARD_OPTIONS.delivery}
          apiData={metrics?.delivery}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
        <QualityCard
          options={CARD_OPTIONS.quality}
          apiData={metrics?.quality}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
        <EquipmentCard
          options={CARD_OPTIONS.equipment}
          apiData={metrics?.equipment}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
        <AttendanceCard
          options={CARD_OPTIONS.attendance}
          apiData={metrics?.attendance}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />
      </div>
    </div>
  );
}
