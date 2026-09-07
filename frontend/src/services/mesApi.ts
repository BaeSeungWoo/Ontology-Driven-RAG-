import api from "@/services/api";

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

export async function getMesDashboardViews(): Promise<MesDashboardViews> {
  const response = await api.get<{ views: MesDashboardViews }>("/api/mes/dashboard");
  return response.data.views;
}

export async function generateMesReport(views: MesDashboardViews): Promise<MesReport> {
  const response = await api.post<{ report: MesReport }>("/api/mes/report", {
    config: "ollama_config",
    productionTrendRows: views["mes2-production-trend-14d"] ?? [],
    deliveryRiskCardRows: views["mes2-card-delivery-risk"] ?? [],
    deliveryRiskDetailRows: views["mes2-delivery-risk-detail"] ?? [],
    equipmentWeeklyRows: views["machine-operation-rate-weekly"] ?? [],
    qualityInstrumentRows: views["mes2-quality-instrument-management"] ?? [],
  });
  return response.data.report;
}
