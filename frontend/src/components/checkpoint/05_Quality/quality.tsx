"use client";

import { useMemo, useState } from "react";
import type {
  QualityCustomerImpactRowApi,
  QualityDefectCompositionRowApi,
  QualityMetricsApi,
  QualityProcessRowApi,
  QualityRiskRowApi,
  Section05,
} from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import SectionTable, { type TableColumn } from "../sectionTable";
import SectionTabs, { type SectionTabItem } from "../sectionTabs";

type Section05Props = {
  section05Data?: Section05;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function QualitySection({
  section05Data,
  isLoading = false,
  errorMessage = "",
}: Section05Props) {
  const [activePanel, setActivePanel] = useState<
    "summary" | "process" | "defect" | "risk" | "impact"
  >("summary");
  const tabItems: SectionTabItem<"summary" | "process" | "defect" | "risk" | "impact">[] = [
    { key: "summary", label: "5.1 품질요약" },
    { key: "process", label: "5.2 공정별 품질 현황" },
    { key: "defect", label: "5.3 불량구성" },
    { key: "risk", label: "5.4 품질 리스크" },
    { key: "impact", label: "5.5 고객 영향" },
  ];

  const summaryRows = section05Data?.summary ?? [];
  const processRows = section05Data?.processQual ?? [];
  const defectRows = section05Data?.defect ?? [];
  const riskRows = section05Data?.lisk ?? [];
  const impactRows = section05Data?.custImpact ?? [];

  const summaryColumns: TableColumn<QualityMetricsApi>[] = [
    { header: "총검사수량", render: (row) => row.totalQty, align: "right" },
    { header: "양품수량", render: (row) => row.qty, align: "right" },
    { header: "불량수량", render: (row) => row.defectQty, align: "right" },
    { header: "불량률(%)", render: (row) => row.defectRate, align: "right" },
    { header: "PPM", render: (row) => row.ppm, align: "right" },
  ];

  const processColumns = useMemo<TableColumn<QualityProcessRowApi>[]>(
    () => [
      { header: "공정", render: (row) => row.defectProc ?? "-", align: "left" },
      { header: "설비", render: (row) => row.equipName ?? "-", align: "left" },
      { header: "공정코드", render: (row) => row.processCode ?? "-", align: "left" },
      { header: "공정명", render: (row) => row.processName ?? "-", align: "left" },
      { header: "불량수량", render: (row) => row.defectQty, align: "right" },
      { header: "불량률(%)", render: (row) => row.defectRate, align: "right" },
    ],
    []
  );

  const defectColumns = useMemo<TableColumn<QualityDefectCompositionRowApi>[]>(
    () => [
      { header: "불량결과", render: (row) => row.result ?? "-", align: "left" },
      { header: "불량수량", render: (row) => row.defectQty, align: "right" },
      { header: "구성비", render: (row) => row.defectRatio ?? "-", align: "right" },
    ],
    []
  );

  const riskColumns = useMemo<TableColumn<QualityRiskRowApi>[]>(
    () => [
      { header: "수주번호", render: (row) => row.orderNo ?? "-", align: "left" },
      { header: "행번", render: (row) => row.orderDetailNo, align: "right" },
      { header: "품목코드", render: (row) => row.itemCode ?? "-", align: "left" },
      { header: "품명", render: (row) => row.itemName ?? "-", align: "left" },
      { header: "고객", render: (row) => row.customerName ?? "-", align: "left" },
      { header: "납기일", render: (row) => row.delvDate ?? "-", align: "left" },
      { header: "불량수량", render: (row) => row.defectQty, align: "right" },
      { header: "불량결과", render: (row) => row.result ?? "-", align: "left" },
      { header: "리스크율(%)", render: (row) => row.liskRate, align: "right" },
      { header: "위험여부", render: (row) => row.danger ?? "-", align: "left" },
    ],
    []
  );

  const impactColumns = useMemo<TableColumn<QualityCustomerImpactRowApi>[]>(
    () => [
      { header: "검사지시번호", render: (row) => row.inspNum ?? "-", align: "left" },
      { header: "작업지시번호", render: (row) => row.workNum ?? "-", align: "left" },
      { header: "수주번호", render: (row) => row.orderNo ?? "-", align: "left" },
      { header: "행번", render: (row) => row.orderDetailNo, align: "right" },
      { header: "품목코드", render: (row) => row.itemCode ?? "-", align: "left" },
      { header: "품명", render: (row) => row.itemName ?? "-", align: "left" },
      { header: "불량분류", render: (row) => row.defectType ?? "-", align: "left" },
      { header: "불량원인", render: (row) => row.cause ?? "-", align: "left" },
      { header: "불량수량", render: (row) => row.defectQty, align: "right" },
      { header: "고객명", render: (row) => row.customerName ?? "-", align: "left" },
    ],
    []
  );

  return (
    <article className={styles.card}>
      <h2>5. 품질 현황 (Quality)</h2>

      <div className={styles.sectionFrame}>
        <SectionTabs
          items={tabItems}
          activeKey={activePanel}
          onChange={setActivePanel}
          ariaLabel="품질현황 섹션 선택"
          variant="section"
        />

        {activePanel === "summary" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>5.1 품질요약</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section05Data?.summaryComment ?? "-"}
            </p>
            <SectionTable columns={summaryColumns} rows={summaryRows} rowKey={(_, i) => `qual-summary-${i}`} />
          </div>
        ) : null}

        {activePanel === "process" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>5.2 공정별 품질 현황</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section05Data?.processQualComment ?? "-"}
            </p>
            <SectionTable columns={processColumns} rows={processRows} rowKey={(_, i) => `qual-process-${i}`} />
          </div>
        ) : null}

        {activePanel === "defect" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>5.3 불량구성</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section05Data?.defectComment ?? "-"}
            </p>
            <SectionTable columns={defectColumns} rows={defectRows} rowKey={(_, i) => `qual-defect-${i}`} />
          </div>
        ) : null}

        {activePanel === "risk" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>5.4 품질 리스크</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section05Data?.liskComment ?? "-"}
            </p>
            <SectionTable columns={riskColumns} rows={riskRows} rowKey={(_, i) => `qual-risk-${i}`} />
          </div>
        ) : null}

        {activePanel === "impact" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>5.5 고객 영향</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section05Data?.custImpactComment ?? "-"}
            </p>
            <SectionTable columns={impactColumns} rows={impactRows} rowKey={(_, i) => `qual-impact-${i}`} />
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className={styles.metricsDebugError}>{errorMessage}</p> : null}
    </article>
  );
}
