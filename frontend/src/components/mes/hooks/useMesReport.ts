import { useEffect, useState } from "react";
import type { ReportModel } from "@/types/report";
import { TEST_REPORT_DATE } from "@/components/dailyReport/reportDatePicker";
import { getMesSavedReport, startMesSavedReport, type MesSavedReport } from "@/services/mesApi";

export function useMesReport(reportDate: string) {
  const [saved, setSaved] = useState<MesSavedReport | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isStarting, setIsStarting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        let result = await getMesSavedReport(reportDate);
        if (!mounted) return;
        if (!result && reportDate === TEST_REPORT_DATE) result = await startMesSavedReport("vllm_config", reportDate);
        if (mounted) setSaved(result);
      } catch (error) {
        if (mounted) setErrorMessage(error instanceof Error ? error.message : "저장된 MES 리포트를 불러오지 못했습니다.");
      } finally {
        if (mounted) setIsLoading(false);
      }
    };
    void load();
    return () => { mounted = false; };
  }, [reportDate]);

  useEffect(() => {
    if (saved?.status !== "GENERATING" || errorMessage) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getMesSavedReport(reportDate);
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

  const generateReport = async (config: ReportModel) => {
    setIsStarting(true);
    setErrorMessage("");
    try {
      setSaved(await startMesSavedReport(config, reportDate, true));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "MES 리포트를 생성하지 못했습니다.");
    } finally {
      setIsStarting(false);
    }
  };

  return {
    saved,
    views: saved?.views ?? null,
    report: saved?.report ?? null,
    isLoading,
    isReportLoading: isStarting || (saved?.status === "GENERATING" && !errorMessage),
    errorMessage: errorMessage || saved?.errorMessage || "",
    generateReport,
  };
}
