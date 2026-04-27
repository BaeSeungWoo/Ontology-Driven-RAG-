import api from "@/services/api";
import type { CheckPointSectionsRequest, CheckPointSectionsResponse } from "@/types/checkpoint";

export async function getCheckPointSections(
  payload: CheckPointSectionsRequest
): Promise<CheckPointSectionsResponse> {
  const response = await api.post<CheckPointSectionsResponse>("/api/checkpoint/getCheckPointSections", payload);
  return response.data;
}