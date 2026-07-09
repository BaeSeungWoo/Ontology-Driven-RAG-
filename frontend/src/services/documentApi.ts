import api, { API_BASE_URL } from "@/services/api";
import type { ResolvedDocument } from "@/types/chatApi";

function toBackendUrl(path: string) {
  if (/^https?:\/\//i.test(path)) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function resolveDocument(
  sourceDocName: string,
  pageRange?: string | null
): Promise<ResolvedDocument> {
  const response = await api.get<ResolvedDocument>("/api/documents/resolve", {
    params: {
      source_doc_name: sourceDocName,
      page_range: pageRange || undefined,
    },
  });

  return {
    ...response.data,
    asset_url: toBackendUrl(response.data.asset_url),
  };
}
