"use client";

import { useState } from "react";
import type { EquipmentBottleneckRowApi, EquipmentUtilizationRowApi, Section02 } from "@/types/checkpoint";
import styles from "../checkpoint.module.css";
import SectionTable, { type TableColumn } from "../sectionTable";
import SectionTabs, { type SectionTabItem } from "../sectionTabs";

type Section_02_Props = {
  section02Data?: Section02;
  isLoading?: boolean;
  errorMessage?: string;
};

// 숫자형 실적 지표는 천 단위 구분기호로 통일한다.
function formatNumber(value: number) {
  return new Intl.NumberFormat("ko-KR").format(value);
}

// 비율(%)은 소수 1자리로 표현한다.
function formatRate(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return value.toFixed(1);
}

// 시간/손실 값은 정수면 콤마, 소수면 최대 1자리까지 노출한다.
function formatAmount(value?: number) {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return Number.isInteger(value)
    ? formatNumber(value)
    : new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1 }).format(value);
}

export default function ProductionSection({
  section02Data,
  isLoading = false,
  errorMessage = "",
}: Section_02_Props) {
  const [activePanel, setActivePanel] = useState<"summary" | "underperform" | "equipment">("summary");
  const sectionTabItems: SectionTabItem<"summary" | "underperform" | "equipment">[] = [
    { key: "summary", label: "2.1 생산요약" },
    { key: "underperform", label: "2.2 실적미달 LOT" },
    { key: "equipment", label: "2.3 설비 병목 및 가동률" },
  ];

  // 백엔드 Section_02 응답을 섹션별 테이블 데이터로 분리한다.
  const summaryRows = section02Data?.summary ?? [];
  const underperformRows = section02Data?.underperform ?? [];
  const equipmentBottleneckRows = section02Data?.equipmentBottleneck ?? [];
  const equipmentUtilizationRows = section02Data?.equipmentUtilization ?? [];

  // 2.1 생산요약 테이블 컬럼 정의
  const summaryColumns: TableColumn<Section02["summary"][number]>[] = [
    { header: "계획수량(EA)", render: (row) => formatNumber(row.planQty), align: "right" },
    { header: "실적수량(EA)", render: (row) => formatNumber(row.qty), align: "right" },
    { header: "달성률(%)", render: (row) => formatRate(row.achiveRate), align: "right" },
    { header: "총설비수", render: (row) => formatNumber(row.totalEquipQty), align: "right" },
    { header: "가동설비수", render: (row) => formatNumber(row.runningEquipQty), align: "right" },
  ];

  // 2.2 실적미달 LOT 테이블 컬럼 정의
  const underperformColumns: TableColumn<Section02["underperform"][number]>[] = [
    { header: "수주번호", render: (row) => row.orderNo ?? row.lotNo ?? "-", align: "left" },
    { header: "순번", render: (row) => (typeof row.seqNo === "number" ? formatNumber(row.seqNo) : "-"), align: "center" },
    { header: "품목코드", render: (row) => row.itemCode ?? "-", align: "left" },
    { header: "공정순번", render: (row) => (typeof row.processSeq === "number" ? formatNumber(row.processSeq) : "-"), align: "center" },
    { header: "공정명", render: (row) => row.processName ?? "-", align: "left" },
    { header: "계획수량", render: (row) => formatNumber(row.planQty), align: "right" },
    { header: "실적수량", render: (row) => formatNumber(row.actualQty), align: "right" },
    { header: "달성률", render: (row) => formatRate(row.achiveRate), align: "right" },
  ];

  // 2.3-1 설비 병목 테이블 컬럼 정의
  const equipmentBottleneckColumns: TableColumn<EquipmentBottleneckRowApi>[] = [
    { header: "설비코드", render: (row) => row.equipmentCode ?? "-", align: "left" },
    { header: "설비명", render: (row) => row.equipmentName ?? "-", align: "left" },
    { header: "요구시간", render: (row) => formatAmount(row.requiredTime), align: "right" },
    { header: "가용시간", render: (row) => formatAmount(row.availableTime), align: "right" },
    { header: "초과시간", render: (row) => formatAmount(row.overTime), align: "right" },
    { header: "부하율", render: (row) => formatRate(row.utilization), align: "right" },
  ];

  // 2.3-2 가동률 테이블 컬럼 정의
  const equipmentUtilizationColumns: TableColumn<EquipmentUtilizationRowApi>[] = [
    { header: "설비코드", render: (row) => row.equipmentCode ?? "-", align: "left" },
    { header: "설비명", render: (row) => row.equipmentName ?? "-", align: "left" },
    { header: "가용시간", render: (row) => formatAmount(row.availableTime), align: "right" },
    { header: "가동시간", render: (row) => formatAmount(row.runTime), align: "right" },
    { header: "표준시간", render: (row) => formatAmount(row.standardTime), align: "right" },
    { header: "설비손실", render: (row) => formatAmount(row.equipLoss), align: "right" },
    { header: "작업손실", render: (row) => formatAmount(row.workLoss), align: "right" },
    { header: "계획손실", render: (row) => formatAmount(row.planLoss), align: "right" },
    { header: "가동률", render: (row) => formatRate(row.utilizationRate), align: "right" },
    { header: "계획율", render: (row) => formatRate(row.planRate), align: "right" },
    { header: "효율", render: (row) => formatRate(row.efficiency), align: "right" },
  ];

  return (
    <article className={styles.card}>
      <h2>2. 생산 현황 (Production)</h2>

      <div className={styles.sectionFrame}>
        <SectionTabs
          items={sectionTabItems}
          activeKey={activePanel}
          onChange={setActivePanel}
          ariaLabel="생산현황 섹션 선택"
          variant="section"
        />

        {activePanel === "summary" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>2.1 생산요약</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section02Data?.summaryComment ?? "-"}
            </p>
            <SectionTable
              columns={summaryColumns}
              rows={summaryRows}
              rowKey={(_, index) => `summary-row-${index}`}
            />
          </div>
        ) : null}

        {activePanel === "underperform" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>2.2 실적미달 LOT</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section02Data?.underperformComment ?? "-"}
            </p>
            <SectionTable
              columns={underperformColumns}
              rows={underperformRows}
              rowKey={(_, index) => `underperform-row-${index}`}
            />
          </div>
        ) : null}

        {activePanel === "equipment" ? (
          <div className={styles.sectionPanel}>
            <label className={styles.blockLabel}>2.3 설비 병목 및 가동률</label>
            <p className={styles.summaryComment}>
              {isLoading ? "로딩 중..." : section02Data?.equipComment ?? "-"}
            </p>
            <label className={styles.blockLabel}>설비 병목</label>
            <SectionTable
              columns={equipmentBottleneckColumns}
              rows={equipmentBottleneckRows}
              rowKey={(_, index) => `equip-bottleneck-row-${index}`}
            />
            <br/>
            <label className={styles.blockLabel}>가동률</label>
            <SectionTable
              columns={equipmentUtilizationColumns}
              rows={equipmentUtilizationRows}
              rowKey={(_, index) => `equip-utilization-row-${index}`}
            />
          </div>
        ) : null}
      </div>

      {errorMessage ? <p className={styles.metricsDebugError}>{errorMessage}</p> : null}
    </article>
  );
}
