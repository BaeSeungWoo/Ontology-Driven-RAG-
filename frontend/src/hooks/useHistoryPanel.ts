import { useCallback, useEffect, useRef, useState } from "react";
import type { HistoryItem } from "@/components/chat/history/historyCard";
import { getHistoryPagination } from "@/services/historyApi";
import type { HistoryResponse } from "@/types/historyApi";
import { LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS } from "@/constants/llmOptions";

/**
 * 기능: 서버 날짜 문자열을 카드 표기용 포맷으로 변환
 * 목적: 이력 카드의 시간 표시 형식을 일관되게 유지
 * In: value(string | undefined)
 * Out: formattedDateTime(string)
 */
function formatDateTime(value: string | undefined): string {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const yy = String(date.getFullYear()).slice(-2);
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const hh = String(date.getHours()).padStart(2, "0");
  const mi = String(date.getMinutes()).padStart(2, "0");
  return `${yy}-${mm}-${dd} ${hh}:${mi}`;
}

/**
 * 기능: 히스토리 API row를 UI 카드 타입으로 정규화
 * 목적: 카드 표시에 필요한 라벨과 세션 동기화에 필요한 원본 메타를 함께 구성한다.
 * In: row(HistoryResponse), selectedSessionId
 * Out: HistoryItem
 */
export function toHistoryItem(row: HistoryResponse, selectedSessionId: number | null): HistoryItem {
  const id = Number(row.sessionId);
  const llmModelLabel =
    LLM_MODEL_OPTIONS.find((option) => option.value === row.llmModel)?.label ?? row.llmModel;
  const llmModeLabel =
    LLM_MODE_OPTIONS.find((option) => option.value === row.llmMode)?.label ?? row.llmMode;

  return {
    id,
    title: row.title ?? "제목 없음",
    questioner: row.questioner ?? "-",
    llmModel: row.llmModel ?? "",
    llmMode: row.llmMode ?? "",
    promptNo: Number.isFinite(Number(row.promptNo)) ? Number(row.promptNo) : null,
    llmModelLabel,
    llmModeLabel,
    promptName: row.promptName ?? "-",
    personaType: row.personaType,
    recentAt: formatDateTime(row.updatedAt ?? row.createdAt),
    recentAtTimestamp: Date.parse(row.updatedAt ?? row.createdAt),
    isActive: selectedSessionId === id,
  };
}

export function useHistoryPanel({ selectedSessionId, refreshKey }: {
  selectedSessionId: number | null;
  refreshKey: number;
}) {
  const [rows, setRows] = useState<HistoryResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState("");
  const cursor = useRef({ page: 0, totalPages: 1, loading: false });

  const loadMore = useCallback(async () => {
    const current = cursor.current;
    if (current.loading || current.page >= current.totalPages) return;
    current.loading = true;
    setIsLoading(true);
    setError("");
    try {
      const response = await getHistoryPagination({ page: current.page + 1, page_size: 20 });
      if (cursor.current !== current) return;
      setRows(previous => {
        const merged = new Map(previous.map(row => [row.sessionId, row]));
        response.rows.forEach(row => merged.set(row.sessionId, row));
        return Array.from(merged.values());
      });
      current.page = response.page;
      current.totalPages = response.total_pages;
      setHasMore(response.rows.length > 0 && current.page < current.totalPages);
      if (!response.rows.length) current.totalPages = current.page;
    } catch {
      if (cursor.current === current) setError("이력을 불러오지 못했습니다. 다시 시도해주세요.");
    } finally {
      if (cursor.current === current) {
        current.loading = false;
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    cursor.current = { page: 0, totalPages: 1, loading: false };
    setRows([]);
    setHasMore(true);
    void loadMore();
    return () => { cursor.current = { ...cursor.current }; };
  }, [refreshKey, loadMore]);

  return {
    historyItems: rows.map(row => toHistoryItem(row, selectedSessionId)),
    isLoading, hasMore, error, loadMore,
  };
}
