import api from "@/services/api";
import type { DailyReportSectionsApi, DailyReportSectionsRequest } from "@/types/dailyReport";

async function postDailyReport<TResponse>(
  endpoint: string,
  payload: DailyReportSectionsRequest,
): Promise<TResponse> {
  const response = await api.post<TResponse>(endpoint, payload);
  return response.data;
}

export async function getReportSections(
  payload: DailyReportSectionsRequest,
): Promise<DailyReportSectionsApi> {
  return postDailyReport<DailyReportSectionsApi>("/api/dailyReport/getReportSections", payload);
}
