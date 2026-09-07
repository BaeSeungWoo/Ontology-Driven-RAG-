"use client";

import { useRef } from "react";
import { type MesKeyIssue, type MesManagementAction, type MesViewRow } from "@/services/mesApi";
import { exportHtmlSnapshot, printHtmlSnapshot } from "@/utils/exportHtmlSnapshot";
import styles from "../mes.module.css";
import KeyIssuesTop3 from "./00_Summary/keyIssuesTop3";
import OverallOperationSummary from "./00_Summary/overallOperationSummary";
import SummaryMetrics from "./00_Summary/summaryMetrics";
import TodayManagementActions from "./00_Summary/todayManagementActions";
import DeliveryRiskOrders from "./01_Contents/01_DeliveryRiskOrders";
import SevenDayForecast from "./01_Contents/02_SevenDayForecast";
import ProductionResultTrend from "./01_Contents/03_ProductionResultTrend";
import Quality from "./01_Contents/05_Quality";
import EquipmentOperationRate from "./01_Contents/04_EquipmentOperationRate";
import { getReportDateKey } from "./reportUtils";

type MesExecutiveReportProps = {
  productionResultRows: MesViewRow[];
  incompleteWorkRows: MesViewRow[];
  deliveryRiskCardRows: MesViewRow[];
  deliveryRiskDetailRows: MesViewRow[];
  deliveryDelayForecastRows: MesViewRow[];
  workDepletionForecastRows: MesViewRow[];
  productionTrendRows: MesViewRow[];
  qualityInstrumentRows: MesViewRow[];
  machineOperationRateWeeklyRows: MesViewRow[];
  inspectionRows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
  overallSummary: string;
  keyIssues: MesKeyIssue[];
  managementActions: MesManagementAction[];
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
  point_prodTrend: string;
  point_deliveryRisk: string;
  point_equipRate: string;
  point_quality: string;
};

function formatReportDate(value: string): string {
  return value ? value.replace(/-/g, ". ") : "-";
}

export default function MesExecutiveReport({
  productionResultRows,
  incompleteWorkRows,
  deliveryRiskCardRows,
  deliveryRiskDetailRows,
  deliveryDelayForecastRows,
  workDepletionForecastRows,
  productionTrendRows,
  qualityInstrumentRows,
  machineOperationRateWeeklyRows,
  inspectionRows,
  isLoading,
  errorMessage,
  overallSummary,
  keyIssues,
  managementActions,
  isSummaryLoading,
  summaryErrorMessage,
  point_prodTrend,
  point_deliveryRisk,
  point_equipRate,
  point_quality,
}: MesExecutiveReportProps) {
  const reportRef = useRef<HTMLElement>(null);
  const latestReportDate = getReportDateKey(
    deliveryRiskCardRows[0]?.REPORT_DATE ?? productionResultRows[0]?.REPORT_DATE,
  );

  const exportHtml = () => {
    if (!reportRef.current) return;
    exportHtmlSnapshot(
      reportRef.current,
      `MES 데일리 리포트 ${latestReportDate}`,
      `MES_데일리리포트_${latestReportDate || "report"}.html`,
    );
  };

  const exportPdf = () => {
    if (!reportRef.current) return;
    printHtmlSnapshot(reportRef.current, `MES 데일리 리포트 ${latestReportDate}`);
  };

  return (
    <section ref={reportRef} className={styles.executiveReport} aria-label="MES 데일리 리포트">
      <header className={styles.executiveHeader}>
        <div>
          <p>MES DAILY REPORT</p>
          <h2>MES 데일리 리포트</h2>
        </div>
        <div className={styles.executiveHeaderActions}>
          <time dateTime={latestReportDate}>
            생성 기준: {formatReportDate(latestReportDate)}
          </time>
          <div className={styles.exportButtons} data-export-control>
            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={exportHtml}
              disabled={isLoading || isSummaryLoading}
            >
              HTML 내보내기
            </button>
            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={exportPdf}
              disabled={isLoading || isSummaryLoading}
            >
              PDF 내보내기
            </button>
          </div>
        </div>
      </header>

      <div className={styles.reportSections}>
        {/* 전체 운영 요약 */}
        <OverallOperationSummary
          overallSummary={overallSummary}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
        {/* 핵심이슈 */}
        <KeyIssuesTop3
          keyIssues={keyIssues}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
        {/* 오늘의 경영 */}
        <TodayManagementActions
          managementActions={managementActions}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />

        {/* 종합 카드 */}
        <SummaryMetrics
          productionResultRows={productionResultRows}
          incompleteWorkRows={incompleteWorkRows}
          deliveryRiskRows={deliveryRiskCardRows}
          machineOperationRateWeeklyRows={machineOperationRateWeeklyRows}
          inspectionRows={inspectionRows}
        />
        {/* 납기 임박 미완료 수주 */}
        <DeliveryRiskOrders
          cardRows={deliveryRiskCardRows}
          detailRows={deliveryRiskDetailRows}
          isLoading={isLoading}
          errorMessage={errorMessage}
          managementPoint={point_deliveryRisk}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
        {/* 향후 7일 전망 */}
        <SevenDayForecast
          deliveryDelayRows={deliveryDelayForecastRows}
          workDepletionRows={workDepletionForecastRows}
          productionTrendRows={productionTrendRows}
          machineOperationRateWeeklyRows={machineOperationRateWeeklyRows}
          isLoading={isLoading}
          errorMessage={errorMessage}
        />

        {/* 생산 실적 추이 */}
        <ProductionResultTrend
          rows={productionTrendRows}
          isLoading={isLoading}
          errorMessage={errorMessage}
          managementPoint={point_prodTrend}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
        {/* 설비별 가동률 */}
        <EquipmentOperationRate
          equipmentWeeklyRows={machineOperationRateWeeklyRows}
          isLoading={isLoading}
          errorMessage={errorMessage}
          managementPoint={point_equipRate}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
        {/* 품질 */}
        <Quality
          rows={qualityInstrumentRows}
          isLoading={isLoading}
          errorMessage={errorMessage}
          managementPoint={point_quality}
          isSummaryLoading={isSummaryLoading}
          summaryErrorMessage={summaryErrorMessage}
        />
      </div>
    </section>
  );
}
