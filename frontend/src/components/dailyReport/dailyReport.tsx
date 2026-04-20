"use client";

import { useEffect, useState } from "react";
import PageTabs from "@/components/navigation/pageTabs";
import ThemeSwitcher, { type ThemeKey } from "@/components/chat/themeSwitcher/themeSwitcher";
import { getReportSections } from "@/services/dailyReportApi";
import type { DailyReportSectionsApi, DailyReportSectionsRequest } from "@/types/dailyReport";
import styles from "./dailyReport.module.css";
import SummarySection from "./01_Summary/summarySection";
import AlertActionsSection from "./02_Alerts_Actions/alertActionsSection";
import MetricsSection from "./03_Metrics/metricsSection";
import CauseAnalysisSection from "./04_Analysis/causeAnalysisSection";

const REPORT_SECTIONS_REQUEST: DailyReportSectionsRequest = {
  date: "2026-03-06",
  reportId: "OBI",
  locale: "ko_KR",
};

export default function DailyReport() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";
  const [sections, setSections] = useState<DailyReportSectionsApi | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let isMounted = true;

    const load = async () => {
      setIsLoading(true);
      setErrorMessage("");

      try {
        const result = await getReportSections(REPORT_SECTIONS_REQUEST);
        if (!isMounted) return;
        setSections(result);
      } catch (error) {
        if (!isMounted) return;
        const message =
          error instanceof Error
            ? error.message
            : "리포트 섹션 데이터를 불러오는 중 오류가 발생했습니다.";
        setErrorMessage(message);
      } finally {
        if (isMounted) setIsLoading(false);
      }
    };

    load();

    return () => {
      isMounted = false;
    };
  }, []);

  return (
    <div className="tw-chat-page">
      <div className="tw-chat-toolbar">
        <div className={styles.reportToolbarLeft}>
          <h1 className="tw-chat-title">Ontology-Driven-RAG</h1>
          <PageTabs />
        </div>
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <main className={styles.reportBody}>
        <section className={styles.reportStack}>
          <SummarySection summary={sections?.summary} isLoading={isLoading} />
          <AlertActionsSection anomalyAction={sections?.anomalyAction} isLoading={isLoading} />
          <MetricsSection metrics={sections?.metrics} isLoading={isLoading} errorMessage={errorMessage} />
          <CauseAnalysisSection analysis={sections?.analysis} isLoading={isLoading} />
        </section>
      </main>
    </div>
  );
}
