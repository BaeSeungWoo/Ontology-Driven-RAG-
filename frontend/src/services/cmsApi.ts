import api from "@/services/api";
import type { ReportModel } from "@/types/report";

export type CmsViewRow = Record<string, unknown>;

export type CmsViewKey =
  | "daily-planned-rate"
  | "hourly-rate"
  | "daily-alarm-summary"
  | "alarm-machine-top3"
  | "longest-alarm-top3";

export type CmsDashboardViews = Record<CmsViewKey, CmsViewRow[]>;

export type CmsReport = {
  generatedAt: string;
  metrics: {
    plannedRate: number | null;
    plannedSeconds: number;
    operateSeconds: number;
    stopSeconds: number;
    alarmSeconds: number;
    offSeconds: number;
    alarmEvents: number;
    alarmTypes: number;
  };
  evaluation: {
    status: "danger" | "warning" | "good";
    label: "위험" | "경고" | "양호";
    description: string;
  };
  weeklyPlannedRates: Array<{
    workDate: string;
    label: string;
    value: number;
    status: "danger" | "warning" | "good";
  }>;
  dailyTotals: Array<{
    workDate: string;
    totalSeconds: number;
    operateSeconds: number;
    stopSeconds: number;
    alarmSeconds: number;
    offSeconds: number;
  }>;
  hourlyRates: Array<{ label: string; value: number }>;
  topAlarms: Array<{ code: string; count: number; machines: string[] }>;
  topAlarmMachines: Array<{
    rank: number;
    machineCode: string;
    machineName: string;
    count: number;
  }>;
  longestAlarms: Array<{
    rank: number;
    machineCode: string;
    machineName: string;
    code: string;
    details: string;
    occurDate: string;
    finishDate: string;
    durationSeconds: number;
  }>;
  executiveSummary: string;
};

export type CmsChatMessage = {
  role: "user" | "assistant";
  content: string;
};

export type CmsSavedReport = {
  factoryId: string;
  reportDate: string;
  status: "GENERATING" | "COMPLETED" | "FAILED";
  config: ReportModel;
  modelName: string;
  report: CmsReport | null;
  views: CmsDashboardViews | null;
  startedAt: string;
  completedAt: string | null;
  errorMessage: string | null;
};

export async function getCmsSavedReport(reportDate: string): Promise<CmsSavedReport | null> {
  const response = await api.get<{ savedReport: CmsSavedReport | null }>("/api/cms/saved-report", { params: { reportDate } });
  return response.data.savedReport;
}

export async function startCmsSavedReport(config: ReportModel, reportDate: string, force = false): Promise<CmsSavedReport> {
  const response = await api.post<{ savedReport: CmsSavedReport }>("/api/cms/saved-report", { config, reportDate, force });
  return response.data.savedReport;
}

export async function askCmsReport(
  question: string,
  history: CmsChatMessage[],
  report: CmsReport,
  config: ReportModel,
): Promise<string> {
  const response = await api.post<{ answer: string }>("/api/cms/chat", {
    question,
    history,
    report,
    config,
  });
  return response.data.answer;
}
