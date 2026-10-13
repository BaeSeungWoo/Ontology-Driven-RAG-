"use client";

import { useState } from "react";
import styles from "@/components/dailyReport/dailyReport.module.css";
import theme from "@/components/dailyReport/reportTheme.module.css";
import ReportDatePicker, { TEST_REPORT_DATE, todayInKorea } from "@/components/dailyReport/reportDatePicker";
import { shiftReportDisplayDates } from "@/components/dailyReport/reportDisplayDates";
import AppHeader from "@/components/navigation/appHeader";
import MesExecutiveReport from "./Report/mesExecutiveReport";
import { useMesReport } from "./hooks/useMesReport";
import mesStyles from "./mes.module.css";

export default function MesPage() {
  const [reportDate, setReportDate] = useState(todayInKorea);
  return <MesReportPage reportDate={reportDate} onDateChange={setReportDate} />;
}

function MesReportPage({ reportDate, onDateChange }: { reportDate: string; onDateChange: (value: string) => void }) {
  const {
    saved,
    views: savedViews,
    report: savedReport,
    isLoading,
    isReportLoading,
    errorMessage,
    generateReport,
  } = useMesReport(TEST_REPORT_DATE);
  const views = shiftReportDisplayDates(savedViews, reportDate);
  const report = shiftReportDisplayDates(savedReport, reportDate);

  return (
    <div className={`tw-chat-page ${theme.page}`}>
      <AppHeader>
        <div className={theme.headerActions}>
          <ReportDatePicker value={reportDate} onChange={onDateChange} disabled />
          <button
            type="button"
            className={theme.reportButton}
            onClick={() => generateReport("vllm_config")}
            disabled
          >
            {isLoading ? "확인 중" : isReportLoading ? "생성 중" : "리포트 생성"}
          </button>
        </div>
      </AppHeader>

      <main className={styles.reportBody}>
        <div className={mesStyles.contentStack}>
          {errorMessage && <p role="alert">{errorMessage}</p>}
          {!isLoading && !saved && !errorMessage && <p className={theme.reportMetadata} role="status">
            저장된 리포트가 없습니다.
          </p>}
          {views && (
            <MesExecutiveReport
              forecastViews={savedViews ?? {}}
              productionResultRows={views?.["mes2-card-production-result"] ?? []}
              incompleteWorkRows={views?.["mes2-card-incomplete-work"] ?? []}
              deliveryRiskCardRows={views?.["mes2-card-delivery-risk"] ?? []}
              deliveryRiskDetailRows={views?.["mes2-delivery-risk-detail"] ?? []}
              deliveryDelayForecastRows={views?.["mes2-forecast-delivery-delay"] ?? []}
              workDepletionForecastRows={views?.["mes2-forecast-work-depletion"] ?? []}
              productionTrendRows={views?.["mes2-production-trend-14d"] ?? []}
              qualityInstrumentRows={views?.["mes2-quality-instrument-management"] ?? []}
              machineOperationRateWeeklyRows={views?.["machine-operation-rate-weekly"] ?? []}
              inspectionRows={views?.["mes2-card-inspection"] ?? []}
              isLoading={isLoading}
              errorMessage={errorMessage}
              overallSummary={report?.overallSummary ?? ""}
              keyIssues={report?.keyIssues ?? []}
              managementActions={report?.managementActions ?? []}
              isSummaryLoading={isReportLoading}
              summaryErrorMessage={errorMessage}
              point_prodTrend={report?.point_prodTrend ?? ""}
              point_deliveryRisk={report?.point_deliveryRisk ?? ""}
              point_equipRate={report?.point_equipRate ?? ""}
              point_quality={report?.point_quality ?? ""}
            />
          )}

        </div>
      </main>
    </div>
  );
}
