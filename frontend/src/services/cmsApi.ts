import api from "@/services/api";

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

export async function getCmsDashboardViews(): Promise<CmsDashboardViews> {
  const response = await api.get<{ views: CmsDashboardViews }>("/api/cms/dashboard");
  return response.data.views;
}

export async function generateCmsReport(): Promise<CmsReport> {
  const response = await api.post<{ report: CmsReport }>("/api/cms/report", {
    config: "ollama_config",
  });
  return response.data.report;
}

export async function askCmsReport(
  question: string,
  history: CmsChatMessage[],
  report: CmsReport,
): Promise<string> {
  const response = await api.post<{ answer: string }>("/api/cms/chat", {
    question,
    history,
    report,
    config: "ollama_config",
  });
  return response.data.answer;
}
