import api from "@/services/api";
import type { ReportModel } from "@/types/report";

export type MesViewRow = Record<string, unknown>;
export type MesDashboardViews = Record<string, MesViewRow[]>;

export type MesKeyIssue = {
  title: string;
  description: string;
};

export type MesManagementAction = {
  priority: string;
  title: string;
  description: string;
};

export type MesReport = {
  generatedAt: string;
  overallSummary: string;
  keyIssues: MesKeyIssue[];
  managementActions: MesManagementAction[];
  point_prodTrend: string;
  point_deliveryRisk?: string;
  point_equipRate: string;
  point_quality: string;
};

export type MesSavedReport = {
  factoryId: string;
  reportDate: string;
  status: "GENERATING" | "COMPLETED" | "FAILED";
  config: ReportModel;
  modelName: string;
  report: MesReport | null;
  views: MesDashboardViews | null;
  startedAt: string;
  completedAt: string | null;
  errorMessage: string | null;
};

export async function getMesSavedReport(reportDate: string): Promise<MesSavedReport | null> {
  const response = await api.get<{ savedReport: MesSavedReport | null }>("/api/mes/saved-report", { params: { reportDate } });
  return response.data.savedReport;
}

export async function startMesSavedReport(config: ReportModel, reportDate: string, force = false): Promise<MesSavedReport> {
  const response = await api.post<{ savedReport: MesSavedReport }>("/api/mes/saved-report", { config, reportDate, force });
  return response.data.savedReport;
}
