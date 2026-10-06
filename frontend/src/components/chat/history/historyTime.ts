export function formatHistoryDateGroup(timestamp: number, now: number): string {
  if (!Number.isFinite(timestamp)) return "날짜 없음";
  const formatter = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" });
  const date = formatter.format(timestamp);
  if (date === formatter.format(now)) return "오늘";
  if (date === formatter.format(now - 86_400_000)) return "어제";
  return date.replaceAll("-", ".");
}
