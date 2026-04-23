"use client";

import { useMemo, useState } from "react";
import type { DelayCauseRowApi, Section03, ShipmentMetricsApi, ShipmentStatusRowApi } from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import SectionTable, { type TableColumn } from "../sectionTable";
import SectionTabs, { type SectionTabItem } from "../sectionTabs";

type Section03Props = {
  section03Data?: Section03;
  isLoading?: boolean;
  errorMessage?: string;
};

export default function ShippingSection({
  section03Data,
  isLoading = false,
  errorMessage = "",
}: Section03Props) {
  const [activePanel, setActivePanel] = useState<"summary" | "statusDelay" | "cause">("summary");
  const sectionTabItems: SectionTabItem<"summary" | "statusDelay" | "cause">[] = [
    { key: "summary", label: "3.1 출하요약" },
    { key: "statusDelay", label: "3.2 출하상태 / 지연 현황" },
    { key: "cause", label: "3.3 지연원인 분석" },
  ];

  const summaryRows = section03Data?.summary ?? [];
  const shipStateRows = section03Data?.shipState ?? [];
  const delayCauseRows = section03Data?.delayCause ?? [];

  const summaryColumns: TableColumn<ShipmentMetricsApi>[] = [
    { header: "계획수량(EA)", render: (row) => row.planQty, align: "right" },
    { header: "출하수량(EA)", render: (row) => row.shipQty, align: "right" },
    { header: "출하금액", render: (row) => row.shipAmt, align: "right" },
    { header: "지연수량(EA)", render: (row) => row.delayQty, align: "right" },
    { header: "평균리드타임", render: (row) => row.leadtimeAVG, align: "right" },
  ];

  const shipStateColumns = useMemo<TableColumn<ShipmentStatusRowApi>[]>(
    () => [
      { header: "수주번호", render: (row) => row.orderNo ?? "-", align: "left" },
      { header: "수주행", render: (row) => row.orderDetailNo, align: "right" },
      { header: "고객명", render: (row) => row.customerName ?? "-", align: "left" },
      { header: "품목코드", render: (row) => row.itemCode ?? "-", align: "left" },
      { header: "품목명", render: (row) => row.itemName ?? "-", align: "left" },
      { header: "계획수량", render: (row) => row.planQty, align: "right" },
      { header: "출하수량", render: (row) => row.shipQty, align: "right" },
      { header: "미출하수량", render: (row) => row.remainQty, align: "right" },
      { header: "출하상태", render: (row) => row.shipState ?? "-", align: "left" },
      { header: "지연일수", render: (row) => row.lateDay, align: "right" },
    ],
    []
  );

  const delayCauseColumns = useMemo<TableColumn<DelayCauseRowApi>[]>(
    () => [
      { header: "수주번호", render: (row) => row.orderNo ?? "-", align: "left" },
      { header: "고객명", render: (row) => row.customerName ?? "-", align: "left" },
      { header: "품목명", render: (row) => row.itemName ?? "-", align: "left" },
      { header: "지연수량", render: (row) => row.delayQty, align: "right" },
      { header: "지연사유", render: (row) => row.delayCause ?? "-", align: "left" },
    ],
    []
  );

  return (
    <article className={styles.card}>
      <h2>3. 출하 현황 (Shipping)</h2>

      <div className={styles.sectionFrame}>
        <SectionTabs
          items={sectionTabItems}
          activeKey={activePanel}
          onChange={setActivePanel}
          ariaLabel="출하현황 섹션 선택"
          variant="section"
        />

        {activePanel === "summary" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>3.1 출하요약</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section03Data?.summaryComment ?? "-"}
            </p>
            <SectionTable
              columns={summaryColumns}
              rows={summaryRows}
              rowKey={(_, index) => `ship-summary-${index}`}
            />
          </div>
        ) : null}

        {activePanel === "statusDelay" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>3.2 출하상태 / 지연 현황</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section03Data?.shipStateComment ?? "-"}
            </p>
            <SectionTable
              columns={shipStateColumns}
              rows={shipStateRows}
              rowKey={(_, index) => `ship-state-${index}`}
            />
          </div>
        ) : null}

        {activePanel === "cause" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>3.3 지연원인 분석</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section03Data?.delayCauseComment ?? "-"}
            </p>
            <SectionTable
              columns={delayCauseColumns}
              rows={delayCauseRows}
              rowKey={(_, index) => `ship-cause-${index}`}
            />
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className={styles.metricsDebugError}>{errorMessage}</p> : null}
    </article>
  );
}
