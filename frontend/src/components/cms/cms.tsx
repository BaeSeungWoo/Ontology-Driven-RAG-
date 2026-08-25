"use client";

import { useEffect, useState } from "react";
import PageTabs from "@/components/navigation/pageTabs";
import ThemeSwitcher, { type ThemeKey } from "@/components/chat/themeSwitcher/themeSwitcher";
import styles from "@/components/dailyReport/dailyReport.module.css";
import {
  generateCmsReport,
  getCmsDashboardViews,
  type CmsDashboardViews,
  type CmsReport,
} from "@/services/cmsApi";
import cmsStyles from "./cms.module.css";
import CmsExecutiveReport from "./Report/cmsExecutiveReport";
import CmsReportChat from "./Report/cmsReportChat";
import CmsViewTable from "./ViewDataTable/cmsViewTable";

const CMS_VIEWS = [
  { viewKey: "daily-planned-rate", title: "최근 7일 계획가동률" },
  { viewKey: "hourly-rate", title: "시간대별 가동률" },
  { viewKey: "daily-alarm-summary", title: "알람히스토리 요약" },
  { viewKey: "alarm-machine-top3", title: "최다 알람 발생 장비 Top 3" },
  { viewKey: "longest-alarm-top3", title: "최장 알람 이력 Top 3" },
] as const;

export default function CmsPage() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";
  const [views, setViews] = useState<CmsDashboardViews | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [isDashboardExpanded, setIsDashboardExpanded] = useState(true);
  const [report, setReport] = useState<CmsReport | null>(null);
  const [isSummaryLoading, setIsSummaryLoading] = useState(false);
  const [summaryErrorMessage, setSummaryErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;

    const loadDashboardViews = async () => {
      try {
        const result = await getCmsDashboardViews();
        if (isMounted) setViews(result);
      } catch (error) {
        if (isMounted) {
          setErrorMessage(
            error instanceof Error ? error.message : "CMS 데이터를 불러오지 못했습니다.",
          );
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadDashboardViews();

    return () => {
      isMounted = false;
    };
  }, []);

  const generateSummary = async () => {
    setIsSummaryLoading(true);
    setSummaryErrorMessage("");

    try {
      setReport(await generateCmsReport());
    } catch (error) {
      setSummaryErrorMessage(
        error instanceof Error ? error.message : "CMS 요약을 생성하지 못했습니다.",
      );
    } finally {
      setIsSummaryLoading(false);
    }
  };

  const dashboardViewCount = views ? Object.keys(views).length : null;

  return (
    <div className="tw-chat-page">
      {/* 상단 탭 */}
      <div className="tw-chat-toolbar">
        <div className={styles.reportToolbarLeft}>
          <h1 className="tw-chat-title">CMS</h1>
          <PageTabs />
        </div>
        {/* 테마 스위치 */}
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <main className={styles.reportBody}>
        <div className={cmsStyles.cmsContentStack}>
          {/* 리포트 생성 버튼 */}
          <section aria-label="전일 운영 요약 생성">
            <button
              type="button"
              className={cmsStyles.reportButton}
              onClick={generateSummary}
              disabled={isSummaryLoading}
            >
              {isSummaryLoading ? "전일 운영 요약 생성 중" : "전일 운영 요약 생성"}
              <span>{isSummaryLoading ? "잠시만 기다려주세요" : "ollama_config"}</span>
            </button>

            {summaryErrorMessage && <p className={cmsStyles.summaryError}>{summaryErrorMessage}</p>}
          </section>

          {/* 리포트 영역 */}
          {report && (
            <section className={cmsStyles.cmsReportLayout} aria-label="리포트 페이지">
              <CmsExecutiveReport report={report} />
              <CmsReportChat report={report} />
            </section>
          )}

          {/* CMS 데이터 영역 */}
          <section className={cmsStyles.dashboardGroup}>
            <button
              type="button"
              className={cmsStyles.dashboardToggle}
              aria-expanded={isDashboardExpanded}
              aria-controls="cms-dashboard-views"
              onClick={() => setIsDashboardExpanded((expanded) => !expanded)}
            >
              <span>
                <small>CMS Data</small>
                <strong>CMS 데이터</strong>
              </span>

              <span className={cmsStyles.dashboardMeta}>
                {isLoading
                  ? "뷰를 불러오는 중"
                  : errorMessage
                    ? "뷰를 불러오지 못함"
                    : `${dashboardViewCount ?? 0}개 뷰`}
                <b aria-hidden="true">{isDashboardExpanded ? "−" : "+"}</b>
              </span>
            </button>

            {/* 뷰 테이블 영역 */}
            {isDashboardExpanded && (
              <div id="cms-dashboard-views" className={cmsStyles.viewList}>
                {CMS_VIEWS.map((view) => (
                  <CmsViewTable
                    key={view.viewKey}
                    {...view}
                    rows={views?.[view.viewKey] ?? null}
                    isLoading={isLoading}
                    errorMessage={errorMessage}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
