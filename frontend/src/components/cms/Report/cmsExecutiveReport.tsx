"use client";

import { useRef } from "react";
import type { CmsReport } from "@/services/cmsApi";
import { exportHtmlSnapshot, exportPdfSnapshot } from "@/utils/exportHtmlSnapshot";
import CmsReportAlarmHistory from "./03_Alarm/cmsReportAlarmHistory";
import CmsReportAlarmInsights from "./03_Alarm/cmsReportAlarmInsights";
import CmsReportMetrics from "./01_DayChangeMetrics/cmsReportMetrics";
import CmsReportOperations from "./02_Operation/cmsReportOperations";
import CmsReportSummary from "./00_Summary/cmsReportSummary";
import { formatReportDate } from "./cmsReportFormatting";
import styles from "../cms.module.css";

type CmsExecutiveReportProps = {
  report: CmsReport;
  isLoading: boolean;
};

export default function CmsExecutiveReport({ report, isLoading }: CmsExecutiveReportProps) {
  const reportRef = useRef<HTMLElement>(null);
  const reportDate = report.weeklyPlannedRates.at(-1)?.workDate;

  const exportHtml = () => {
    if (!reportRef.current) return;
    exportHtmlSnapshot(
      reportRef.current,
      `CMS 데일리 리포트 ${reportDate || ""}`,
      `CMS_데일리리포트_${reportDate || "report"}.html`,
    );
  };

  const exportPdf = async () => {
    if (!reportRef.current) return;
    try {
      await exportPdfSnapshot(
        reportRef.current,
        `CMS 데일리 리포트 ${reportDate || ""}`,
        `CMS_데일리리포트_${reportDate || "report"}.pdf`,
      );
    } catch {
      window.alert("CMS PDF를 생성하지 못했습니다.");
    }
  };

  return (
    <section ref={reportRef} className={styles.executiveReport} aria-label="CMS 데일리 리포트">
      <header className={styles.executiveHeader}>
        <div>
          <p>CMS DAILY REPORT</p>
          <h2>CMS 데일리 리포트</h2>
        </div>
        <div className={styles.executiveHeaderActions}>
          <time dateTime={reportDate}>생성 기준: {formatReportDate(reportDate)}</time>
          <div className={styles.exportButtons} data-export-control>
            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={exportHtml}
              disabled={isLoading}
            >
              HTML 내보내기
            </button>
            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={() => void exportPdf()}
              disabled={isLoading}
            >
              PDF 내보내기
            </button>
          </div>
        </div>
      </header>

      <CmsReportSummary report={report} />
      <CmsReportMetrics report={report} />
      <CmsReportOperations report={report} />
      <CmsReportAlarmHistory report={report} />
      <CmsReportAlarmInsights report={report} />
    </section>
  );
}
