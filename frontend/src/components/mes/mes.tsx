"use client";

import { useState } from "react";
import styles from "@/components/dailyReport/dailyReport.module.css";
import theme from "@/components/dailyReport/reportTheme.module.css";
import ReportModelSelector from "@/components/dailyReport/reportModelSelector";
import ReportDatePicker, { TEST_REPORT_DATE } from "@/components/dailyReport/reportDatePicker";
import type { ReportModel } from "@/types/report";
import AppHeader from "@/components/navigation/appHeader";
import MesExecutiveReport from "./Report/mesExecutiveReport";
import MesViewTable from "./ViewDataTable/mesViewTable";
import { useMesReport } from "./hooks/useMesReport";
import {
  DEFAULT_MES_TAB,
  MES_TABS,
  MES_VIEW_COLUMN_LABELS,
  type MesTabKey,
} from "./mes.constants";
import mesStyles from "./mes.module.css";

export default function MesPage() {
  const [reportDate, setReportDate] = useState(TEST_REPORT_DATE);
  return <MesReportPage key={reportDate} reportDate={reportDate} onDateChange={setReportDate} />;
}

function MesReportPage({ reportDate, onDateChange }: { reportDate: string; onDateChange: (value: string) => void }) {
  const [model, setModel] = useState<ReportModel>("vllm_config");
  const [activeTab, setActiveTab] = useState<MesTabKey>(DEFAULT_MES_TAB);
  const [isDashboardExpanded, setIsDashboardExpanded] = useState(false);
  const {
    saved,
    views,
    report,
    isLoading,
    isReportLoading,
    errorMessage,
    generateReport,
  } = useMesReport(reportDate);
  const activeTabConfig = MES_TABS.find((tab) => tab.key === activeTab)!;

  return (
    <div className={`tw-chat-page ${theme.page}`}>
      <AppHeader>
        <div className={theme.headerActions}>
          <ReportDatePicker value={reportDate} onChange={onDateChange} />
          <ReportModelSelector value={model} onChange={setModel} disabled={isLoading || isReportLoading} />
          <button
            type="button"
            className={theme.reportButton}
            onClick={() => generateReport(model)}
            disabled={isReportLoading || isLoading || reportDate !== TEST_REPORT_DATE}
            title={reportDate !== TEST_REPORT_DATE ? "테스트 데이터는 2026-08-20 기준으로만 생성할 수 있습니다." : undefined}
          >
            {isLoading ? "확인 중" : isReportLoading ? "생성 중" : saved?.status === "COMPLETED" ? "리포트 다시 생성" : saved?.status === "FAILED" || errorMessage ? "리포트 생성 재시도" : "리포트 생성"}
          </button>
        </div>
      </AppHeader>

      <main className={styles.reportBody}>
        <div className={mesStyles.contentStack}>
          <section aria-label="리포트 저장 정보">
            {saved && <p className={theme.reportMetadata}>
              {saved.factoryId} · 기준일 {saved.reportDate} · {saved.modelName}
              {saved.status === "COMPLETED" && saved.completedAt && ` · 저장 완료 ${new Date(saved.completedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`}
            </p>}
            {errorMessage && <p role="alert">{errorMessage}</p>}
            {!isLoading && !saved && !errorMessage && <p className={theme.reportMetadata} role="status">
              {reportDate}에 저장된 리포트가 없습니다. 현재 테스트 데이터는 2026-08-20 기준입니다.
            </p>}
          </section>
          {views && (
            <MesExecutiveReport
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

          {(views || isLoading || isReportLoading) && <section className={mesStyles.viewDataGroup}>
            <button
              type="button"
              className={mesStyles.dashboardHeader}
              aria-expanded={isDashboardExpanded}
              aria-controls="mes-dashboard-views"
              onClick={() => setIsDashboardExpanded((expanded) => !expanded)}
            >
              <span>
                <strong>상세 데이터</strong>
              </span>
              <span className={mesStyles.dashboardMeta}>
                {isLoading || (isReportLoading && !views)
                  ? "데이터를 불러오는 중"
                  : errorMessage
                  ? "데이터를 불러오지 못함"
                    : `${Object.keys(views ?? {}).length}개 데이터 항목`}
                <b aria-hidden="true">{isDashboardExpanded ? "−" : "+"}</b>
              </span>
            </button>

            <div id="mes-dashboard-views" hidden={!isDashboardExpanded}>
            <div className={mesStyles.tabs} role="tablist" aria-label="MES 업무 영역">
              {MES_TABS.map((tab) => (
                <button
                  key={tab.key}
                  id={`mes-tab-${tab.key}`}
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tab.key}
                  aria-controls={`mes-tab-panel-${tab.key}`}
                  className={`${mesStyles.tab} ${activeTab === tab.key ? mesStyles.tabActive : ""}`}
                  onClick={() => setActiveTab(tab.key)}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div
              id={`mes-tab-panel-${activeTab}`}
              role="tabpanel"
              aria-labelledby={`mes-tab-${activeTab}`}
              className={mesStyles.viewList}
            >
              {activeTabConfig.views.map((view) => (
                <MesViewTable
                  key={view.viewKey}
                  {...view}
                  rows={views?.[view.viewKey] ?? null}
                  isLoading={isLoading || (isReportLoading && !views)}
                  errorMessage={errorMessage}
                  columnLabels={MES_VIEW_COLUMN_LABELS[view.viewKey]}
                />
              ))}
            </div>
            </div>
          </section>}
        </div>
      </main>
    </div>
  );
}
