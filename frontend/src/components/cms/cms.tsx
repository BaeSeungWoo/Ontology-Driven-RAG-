"use client";

import { useEffect, useState } from "react";
import AppHeader from "@/components/navigation/appHeader";
import styles from "@/components/dailyReport/dailyReport.module.css";
import theme from "@/components/dailyReport/reportTheme.module.css";
import ReportModelSelector from "@/components/dailyReport/reportModelSelector";
import ReportDatePicker, { TEST_REPORT_DATE } from "@/components/dailyReport/reportDatePicker";
import type { ReportModel } from "@/types/report";
import {
  getCmsSavedReport,
  startCmsSavedReport,
  type CmsSavedReport,
} from "@/services/cmsApi";
import cmsStyles from "./cms.module.css";
import CmsExecutiveReport from "./Report/cmsExecutiveReport";
import CmsViewTable from "./ViewDataTable/cmsViewTable";

const CMS_VIEWS = [
  { viewKey: "daily-planned-rate", title: "최근 7일 계획가동률" },
  { viewKey: "hourly-rate", title: "시간대별 가동률" },
  { viewKey: "daily-alarm-summary", title: "알람히스토리 요약" },
  { viewKey: "alarm-machine-top3", title: "최다 알람 발생 장비 Top 3" },
  { viewKey: "longest-alarm-top3", title: "최장 알람 이력 Top 3" },
] as const;

export default function CmsPage() {
  const [reportDate, setReportDate] = useState(TEST_REPORT_DATE);
  return <CmsReportPage key={reportDate} reportDate={reportDate} onDateChange={setReportDate} />;
}

function CmsReportPage({ reportDate, onDateChange }: { reportDate: string; onDateChange: (value: string) => void }) {
  const [model, setModel] = useState<ReportModel>("vllm_config");
  const [saved, setSaved] = useState<CmsSavedReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [isDashboardExpanded, setIsDashboardExpanded] = useState(false);
  const [isStarting, setIsStarting] = useState(false);
  const views = saved?.views ?? null;
  const report = saved?.report ?? null;
  const isSummaryLoading = isStarting || (saved?.status === "GENERATING" && !errorMessage);
  const summaryErrorMessage = errorMessage || saved?.errorMessage || "";

  useEffect(() => {
    let isMounted = true;

    const loadSavedReport = async () => {
      try {
        let result = await getCmsSavedReport(reportDate);
        if (!isMounted) return;
        if (!result && reportDate === TEST_REPORT_DATE) result = await startCmsSavedReport("vllm_config", reportDate);
        if (isMounted) {
          setSaved(result);
        }
      } catch (error) {
        if (isMounted) {
          setErrorMessage(
            error instanceof Error ? error.message : "저장된 CMS 리포트를 불러오지 못했습니다.",
          );
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    loadSavedReport();

    return () => {
      isMounted = false;
    };
  }, [reportDate]);

  useEffect(() => {
    if (saved?.status !== "GENERATING" || errorMessage) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getCmsSavedReport(reportDate);
        if (stopped) return;
        if (!result) throw new Error("저장된 리포트를 찾을 수 없습니다.");
        setSaved(result);
        if (result.status === "GENERATING") timer = setTimeout(poll, 1500);
      } catch (error) {
        if (!stopped) setErrorMessage(error instanceof Error ? error.message : "리포트 상태를 확인하지 못했습니다.");
      }
    };
    timer = setTimeout(poll, 1500);
    return () => { stopped = true; clearTimeout(timer); };
  }, [saved?.status, errorMessage, reportDate]);

  const generateSummary = async () => {
    setIsStarting(true);
    setErrorMessage("");

    try {
      const result = await startCmsSavedReport(model, reportDate, true);
      setSaved(result);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "CMS 요약을 생성하지 못했습니다.",
      );
    } finally {
      setIsStarting(false);
    }
  };

  const dashboardViewCount = views ? Object.keys(views).length : null;

  return (
    <div className={`tw-chat-page ${theme.page} ${cmsStyles.productionPage}`}>
      {/* 상단 탭 */}
      <AppHeader>
        <div className={theme.headerActions}>
          <ReportDatePicker value={reportDate} onChange={onDateChange} />
          <ReportModelSelector value={model} onChange={setModel} disabled={isLoading || isSummaryLoading} />
          <button
            type="button"
            className={theme.reportButton}
            onClick={generateSummary}
            disabled={isSummaryLoading || isLoading || reportDate !== TEST_REPORT_DATE}
            title={reportDate !== TEST_REPORT_DATE ? "테스트 데이터는 2026-08-20 기준으로만 생성할 수 있습니다." : undefined}
          >
            {isLoading ? "확인 중" : isSummaryLoading ? "생성 중" : saved?.status === "COMPLETED" ? "리포트 다시 생성" : saved?.status === "FAILED" || errorMessage ? "리포트 생성 재시도" : "리포트 생성"}
          </button>
        </div>
      </AppHeader>

      <main className={`${styles.reportBody} ${cmsStyles.productionBody}`}>
        <div className={cmsStyles.cmsContentStack}>
          <section aria-label="리포트 저장 정보">
            {saved && (
              <p className={theme.reportMetadata}>
                {saved.factoryId} · 기준일 {saved.reportDate} · {saved.modelName}
                {saved.status === "COMPLETED" && saved.completedAt && ` · 저장 완료 ${new Date(saved.completedAt).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" })}`}
              </p>
            )}

            {summaryErrorMessage && <p className={cmsStyles.summaryError}>{summaryErrorMessage}</p>}
            {!isLoading && !saved && !errorMessage && (
              <p className={theme.reportMetadata} role="status">{reportDate}에 저장된 리포트가 없습니다. 현재 테스트 데이터는 2026-08-20 기준입니다.</p>
            )}
          </section>

          {/* 리포트 영역 */}
          {report && (
            <section className={cmsStyles.cmsReportLayout} aria-label="리포트 페이지">
              <CmsExecutiveReport report={report} isLoading={isSummaryLoading} summaryError={summaryErrorMessage} config={model} />
            </section>
          )}

          {/* CMS 데이터 영역 */}
          {(views || isLoading || isSummaryLoading) && <section className={cmsStyles.dashboardGroup}>
            <button
              type="button"
              className={cmsStyles.dashboardToggle}
              aria-expanded={isDashboardExpanded}
              aria-controls="cms-dashboard-views"
              onClick={() => setIsDashboardExpanded((expanded) => !expanded)}
            >
              <span>
                <strong>상세 데이터</strong>
              </span>

              <span className={cmsStyles.dashboardMeta}>
                {isLoading || (isSummaryLoading && !views)
                  ? "뷰를 불러오는 중"
                  : errorMessage
                    ? "뷰를 불러오지 못함"
                    : `${dashboardViewCount ?? 0}개 데이터 항목`}
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
                    isLoading={isLoading || (isSummaryLoading && !views)}
                    errorMessage={errorMessage}
                  />
                ))}
              </div>
            )}
          </section>}
        </div>
      </main>
    </div>
  );
}
