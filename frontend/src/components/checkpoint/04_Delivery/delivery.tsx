"use client";

import { useMemo, useState } from "react";
import type { DeliveryIssueRowApi, DeliveryMetricsApi, Section04 } from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import SectionTabs, { type SectionTabItem } from "../sectionTabs";
import SectionTable, { type TableColumn } from "../sectionTable";

type Section04Props = {
  section04Data?: Section04;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function DeliverySection({
  section04Data,
  isLoading = false,
  errorMessage = "",
}: Section04Props) {
  const [activePanel, setActivePanel] = useState<"summary" | "issues">("summary");
  const tabItems: SectionTabItem<"summary" | "issues">[] = [
    { key: "summary", label: "4.1 납기요약" },
    { key: "issues", label: "4.2 납기이슈" },
  ];

  const summaryRows = section04Data?.summary ?? [];
  const issueRows: DeliveryIssueRowApi[] = section04Data?.issues ?? [];

  const summaryColumns: TableColumn<DeliveryMetricsApi>[] = [
    { header: "전체건수", render: (row) => row.totalCnt, align: "right" },
    { header: "정상건수", render: (row) => row.passCnt, align: "right" },
    { header: "위험건수", render: (row) => row.dangerCnt, align: "right" },
    { header: "지연건수", render: (row) => row.delayCnt, align: "right" },
    { header: "납기율(%)", render: (row) => row.delvRate, align: "right" },
  ];

  const issueColumns = useMemo<TableColumn<DeliveryIssueRowApi>[]>(
    () => [
      { header: "수주번호", render: (row) => row.orderNo ?? "-", align: "left" },
      { header: "순번", render: (row) => row.orderDetailNo, align: "right" },
      { header: "품목", render: (row) => row.itemName ?? "-", align: "left" },
      { header: "지연일", render: (row) => row.delayDay, align: "right" },
      { header: "부족수량", render: (row) => row.requireQty, align: "right" },
      { header: "원인", render: (row) => row.cause ?? "-", align: "left" },
      { header: "공정", render: (row) => row.process ?? "-", align: "left" },
      { header: "우선순위", render: (row) => row.rank ?? "-", align: "left" },
      { header: "조치기한", render: (row) => row.actionDate ?? "-", align: "left" },
      { header: "담당부서", render: (row) => row.part ?? "-", align: "left" },
    ],
    []
  );

  return (
    <article className={styles.card}>
      <h2>4. 납기 현황 (Delivery)</h2>

      <div className={styles.sectionFrame}>
        <SectionTabs
          items={tabItems}
          activeKey={activePanel}
          onChange={setActivePanel}
          ariaLabel="납기현황 섹션 선택"
          variant="section"
        />

        {activePanel === "summary" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>4.1 납기요약</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section04Data?.summaryComment ?? "-"}
            </p>
            <SectionTable
              columns={summaryColumns}
              rows={summaryRows}
              rowKey={(_, index) => `delivery-summary-${index}`}
            />
          </div>
        ) : null}

        {activePanel === "issues" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>4.2 납기이슈</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section04Data?.issuesComment ?? "-"}
            </p>
            <SectionTable
              columns={issueColumns}
              rows={issueRows}
              rowKey={(_, index) => `delivery-issues-${index}`}
            />
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className={styles.metricsDebugError}>{errorMessage}</p> : null}
    </article>
  );
}
