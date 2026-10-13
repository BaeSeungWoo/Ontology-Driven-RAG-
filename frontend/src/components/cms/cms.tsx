"use client";

import { useEffect, useState } from "react";
import AppHeader from "@/components/navigation/appHeader";
import styles from "@/components/dailyReport/dailyReport.module.css";
import theme from "@/components/dailyReport/reportTheme.module.css";
import ReportDatePicker, { TEST_REPORT_DATE, todayInKorea } from "@/components/dailyReport/reportDatePicker";
import { shiftReportDisplayDates } from "@/components/dailyReport/reportDisplayDates";
import {
  getCmsSavedReport,
  startCmsSavedReport,
  type CmsSavedReport,
} from "@/services/cmsApi";
import cmsStyles from "./cms.module.css";
import CmsExecutiveReport from "./Report/cmsExecutiveReport";

export default function CmsPage() {
  const [reportDate, setReportDate] = useState(todayInKorea);
  return <CmsReportPage reportDate={reportDate} onDateChange={setReportDate} />;
}

function CmsReportPage({ reportDate, onDateChange }: { reportDate: string; onDateChange: (value: string) => void }) {
  const [saved, setSaved] = useState<CmsSavedReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");
  const [isStarting, setIsStarting] = useState(false);
  const report = shiftReportDisplayDates(saved?.report ?? null, reportDate);
  const isSummaryLoading = isStarting || (saved?.status === "GENERATING" && !errorMessage);
  const summaryErrorMessage = errorMessage || saved?.errorMessage || "";

  useEffect(() => {
    let isMounted = true;

    const loadSavedReport = async () => {
      try {
        let result = await getCmsSavedReport(TEST_REPORT_DATE);
        if (!isMounted) return;
        if (!result) result = await startCmsSavedReport("vllm_config", TEST_REPORT_DATE);
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
  }, []);

  useEffect(() => {
    if (saved?.status !== "GENERATING" || errorMessage) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getCmsSavedReport(TEST_REPORT_DATE);
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
  }, [saved?.status, errorMessage]);

  const generateSummary = async () => {
    setIsStarting(true);
    setErrorMessage("");

    try {
      const result = await startCmsSavedReport("vllm_config", TEST_REPORT_DATE, true);
      setSaved(result);
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "CMS 요약을 생성하지 못했습니다.",
      );
    } finally {
      setIsStarting(false);
    }
  };

  return (
    <div className={`tw-chat-page ${theme.page} ${cmsStyles.productionPage}`}>
      {/* 상단 탭 */}
      <AppHeader>
        <div className={theme.headerActions}>
          <ReportDatePicker value={reportDate} onChange={onDateChange} disabled />
          <button
            type="button"
            className={theme.reportButton}
            onClick={generateSummary}
            disabled
          >
            {isLoading ? "확인 중" : isSummaryLoading ? "생성 중" : "리포트 생성"}
          </button>
        </div>
      </AppHeader>

      <main className={`${styles.reportBody} ${cmsStyles.productionBody}`}>
        <div className={cmsStyles.cmsContentStack}>
          {summaryErrorMessage && <p className={cmsStyles.summaryError}>{summaryErrorMessage}</p>}
          {!isLoading && !saved && !errorMessage && (
            <p className={theme.reportMetadata} role="status">저장된 리포트가 없습니다.</p>
          )}

          {/* 리포트 영역 */}
          {report && (
            <section className={cmsStyles.cmsReportLayout} aria-label="리포트 페이지">
              <CmsExecutiveReport report={report} isLoading={isSummaryLoading} summaryError={summaryErrorMessage} config="vllm_config" />
            </section>
          )}

        </div>
      </main>
    </div>
  );
}
