"use client";

import { useRef } from "react";
import { Download, FileText } from "lucide-react";
import CmsReportChat from "./cmsReportChat";
import type { ReportModel } from "@/types/report";
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
  summaryError: string;
  config: ReportModel;
};

export default function CmsExecutiveReport({ report, isLoading, summaryError, config }: CmsExecutiveReportProps) {
  const reportRef = useRef<HTMLElement>(null);
  const reportDate = report.weeklyPlannedRates.at(-1)?.workDate;

  const exportHtml = () => {
    if (!reportRef.current) return;
    exportHtmlSnapshot(
      reportRef.current,
      `AI 데일리 생산 리포트 ${reportDate || ""}`,
      `AI_데일리_생산_리포트_${reportDate || "report"}.html`,
    );
  };

  const exportPdf = async () => {
    if (!reportRef.current) return;
    try {
      await exportPdfSnapshot(
        reportRef.current,
        `AI 데일리 생산 리포트 ${reportDate || ""}`,
        `AI_데일리_생산_리포트_${reportDate || "report"}.pdf`,
      );
    } catch {
      window.alert("CMS PDF를 생성하지 못했습니다.");
    }
  };

  return (
    <>
    <section ref={reportRef} className={`${styles.executiveReport} ${styles.managementReport}`} aria-label="AI 데일리 생산 리포트">
      <header className={styles.executiveHeader}>
        <div>
          <span className={styles.reportEyebrow}>AI DAILY PRODUCTION REPORT</span>
          <h2>AI 데일리 생산 리포트</h2>
          <p className={styles.reportSubtitle}>생산 현황과 설비 운영 분석</p>
        </div>
        <div className={styles.reportHeaderMeta}>
          <time dateTime={reportDate}>생성 기준: {formatReportDate(reportDate)}</time>
          <span>PRODUCTION SUMMARY</span>
        </div>
      </header>

      <CmsReportMetrics report={report} />
      <CmsReportSummary report={report} isLoading={isLoading} errorMessage={summaryError} />
      <CmsReportOperations report={report} />
      <CmsReportAlarmHistory report={report} />
      <CmsReportAlarmInsights report={report} />
    </section>
    <div className={styles.reportTools}>
        <div className={styles.exportButtons}>

            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={exportHtml}
              disabled={isLoading}
            >
              <FileText size={15} aria-hidden="true" /> HTML 내보내기
            </button>
            <button
              type="button"
              className={styles.htmlExportButton}
              onClick={() => void exportPdf()}
              disabled={isLoading}
            >
              <Download size={15} aria-hidden="true" /> PDF 내보내기
            </button>

        </div>
      <CmsReportChat report={report} config={config} />
    </div>
    </>
  );
}
