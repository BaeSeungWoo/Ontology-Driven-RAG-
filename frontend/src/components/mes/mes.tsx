"use client";

import { useState } from "react";
import ThemeSwitcher, { type ThemeKey } from "@/components/chat/themeSwitcher/themeSwitcher";
import styles from "@/components/dailyReport/dailyReport.module.css";
import PageTabs from "@/components/navigation/pageTabs";
import MesExecutiveReport from "./Report/mesExecutiveReport";
import MesViewTable from "./ViewDataTable/mesViewTable";
import { useMesDashboard } from "./hooks/useMesDashboard";
import { useMesReport } from "./hooks/useMesReport";
import {
  DEFAULT_MES_TAB,
  MES_TABS,
  MES_VIEW_COLUMN_LABELS,
  type MesTabKey,
} from "./mes.constants";
import mesStyles from "./mes.module.css";

const FACTORY_THEME_KEY =
  (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

export default function MesPage() {
  const [activeTab, setActiveTab] = useState<MesTabKey>(DEFAULT_MES_TAB);
  const { views, isLoading, errorMessage } = useMesDashboard();
  const {
    report,
    hasRequested,
    isLoading: isReportLoading,
    errorMessage: reportErrorMessage,
    generateReport,
  } = useMesReport();
  const activeTabConfig = MES_TABS.find((tab) => tab.key === activeTab)!;
  const activeRows = activeTabConfig.views.reduce(
    (count, view) => count + (views?.[view.viewKey]?.length ?? 0),
    0,
  );

  return (
    <div className="tw-chat-page">
      <div className="tw-chat-toolbar">
        <div className={styles.reportToolbarLeft}>
          <h1 className="tw-chat-title">MES</h1>
          <PageTabs />
        </div>
        <ThemeSwitcher initialTheme={FACTORY_THEME_KEY} />
      </div>

      <main className={styles.reportBody}>
        <div className={mesStyles.contentStack}>
          <section aria-label="MES 리포트 생성">
            <button
              type="button"
              className={mesStyles.reportButton}
              onClick={() => generateReport(views)}
              disabled={isReportLoading || isLoading || !views}
            >
              {isReportLoading ? "MES 리포트 생성 중" : "MES 리포트 생성"}
              <span>{isReportLoading ? "잠시만 기다려주세요" : "수주상세 및 생산·출하 경영 포인트"}</span>
            </button>
          </section>

          {hasRequested && (
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
              summaryErrorMessage={reportErrorMessage}
              point_prodTrend={report?.point_prodTrend ?? ""}
              point_deliveryRisk={report?.point_deliveryRisk ?? ""}
              point_equipRate={report?.point_equipRate ?? ""}
              point_quality={report?.point_quality ?? ""}
            />
          )}

          <section className={mesStyles.viewDataGroup}>
            <div className={mesStyles.dashboardHeader}>
              <span>
                <small>MES View Data</small>
                <strong>리포트 사용 뷰 데이터</strong>
              </span>
              <span className={mesStyles.toggleMeta}>
                {isLoading
                  ? "뷰를 불러오는 중"
                  : errorMessage
                  ? "뷰를 불러오지 못함"
                    : `${activeTabConfig.views.length}개 뷰 · ${activeRows}건`}
              </span>
            </div>

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
                  isLoading={isLoading}
                  errorMessage={errorMessage}
                  columnLabels={MES_VIEW_COLUMN_LABELS[view.viewKey]}
                />
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
