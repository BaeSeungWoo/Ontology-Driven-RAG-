import type { CmsReport } from "@/services/cmsApi";
import CmsReportAlarmHistory from "./03_Alarm/cmsReportAlarmHistory";
import CmsReportAlarmInsights from "./03_Alarm/cmsReportAlarmInsights";
import CmsReportMetrics from "./01_DayChangeMetrics/cmsReportMetrics";
import CmsReportOperations from "./02_Operation/cmsReportOperations";
import CmsReportSummary from "./00_Summary/cmsReportSummary";
import { formatReportDate } from "./cmsReportFormatting";
import styles from "../cms.module.css";

type CmsExecutiveReportProps = {
  report: CmsReport;
};

export default function CmsExecutiveReport({ report }: CmsExecutiveReportProps) {
  const reportDate = report.weeklyPlannedRates.at(-1)?.workDate;

  return (
    <section className={styles.executiveReport}>
      <header className={styles.executiveHeader}>
        <div>
          <p>CMS DAILY REPORT</p>
          <h2>CMS 데일리 리포트</h2>
        </div>
        <time dateTime={reportDate}>생성 기준: {formatReportDate(reportDate)}</time>
      </header>

      <CmsReportSummary report={report} />
      <CmsReportMetrics report={report} />
      <CmsReportOperations report={report} />
      <CmsReportAlarmHistory report={report} />
      <CmsReportAlarmInsights report={report} />
    </section>
  );
}
