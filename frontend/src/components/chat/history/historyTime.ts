export function formatHistoryRelativeTime(timestamp: number, now: number): string {
  if (!Number.isFinite(timestamp)) return "-";

  const elapsed = Math.max(0, now - timestamp);
  const date = new Date(timestamp);
  const today = new Date(now);
  const days = Math.round((
    Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) -
    Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())
  ) / 86_400_000);

  if (days === 1) return "어제";
  if (days > 1) return `${days}일 전`;
  if (elapsed < 60_000) return "방금 전";
  if (elapsed < 3_600_000) return `${Math.floor(elapsed / 60_000)}분 전`;
  return `${Math.floor(elapsed / 3_600_000)}시간 전`;
}
