"use client";

import type { Section01 } from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import ProductionCard from "./Cards/01_Production";
import ShipmentCard from "./Cards/02_Shipment";
import DeliveryCard from "./Cards/03_Delivery";
import QualityCard from "./Cards/04_Quality";
import EquipmentCard from "./Cards/05_Equipment";
import AttendanceCard from "./Cards/06_Attendance";

type Section_01_Props = {
  section01Data?: Section01;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function SummarySection({
  section01Data,
  isLoading = false,
  errorMessage = "",
}: Section_01_Props) {
  const keyIssues = section01Data?.keyIssue ?? "-";
  const summaryComment = section01Data?.comment ?? "-";

  return (
    <article className={styles.card}>
      <h2>1. 경영층 요약</h2>
      <p className={styles.summaryComment}>{isLoading ? "로딩 중..." : summaryComment}</p>

      <div className={styles.metricsGrid}>
        <ProductionCard apiData={section01Data?.summary.product} isLoading={isLoading} errorMessage={errorMessage} />
        <ShipmentCard apiData={section01Data?.summary.shipment} isLoading={isLoading} errorMessage={errorMessage} />
        <DeliveryCard apiData={section01Data?.summary.delivery} isLoading={isLoading} errorMessage={errorMessage} />
        <QualityCard apiData={section01Data?.summary.quality} isLoading={isLoading} errorMessage={errorMessage} />
        <EquipmentCard apiData={section01Data?.summary.equipment} isLoading={isLoading} errorMessage={errorMessage} />
        <AttendanceCard apiData={section01Data?.summary.attendance} isLoading={isLoading} errorMessage={errorMessage} />
      </div>

      <br />
      <p className={styles.keyIssuesTitle}>핵심 이슈 TOP 3</p>
      <p className={`${styles.summaryComment} ${styles.keyIssuesText}`}>{isLoading ? "로딩 중..." : keyIssues}</p>
    </article>
  );
}
