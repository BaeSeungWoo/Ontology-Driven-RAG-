export function formatRate(value: number | null) {
  return value === null ? "-" : `${value.toFixed(1)}%`;
}

export function formatHours(seconds: number) {
  const totalMinutes = Math.round(seconds / 60);
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return `${hours.toLocaleString("ko-KR")}시간 ${minutes}분`;
}

export function formatDuration(seconds: number) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainingSeconds = seconds % 60;
  if (hours > 0) return `${hours}시간 ${minutes}분`;
  if (minutes > 0) return `${minutes}분 ${remainingSeconds}초`;
  return `${remainingSeconds}초`;
}

export function formatDateTime(value: string) {
  return value.replace("T", " ").replace(/\.\d+$/, "");
}

export function formatReportDate(workDate: string | undefined) {
  return workDate ? workDate.replaceAll("-", ". ") : "-";
}

export function formatDelta(value: number | null, unit: "point" | "hours") {
  if (value === null) return "전일 데이터 없음";
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const totalMinutes = Math.round(Math.abs(value) * 60);
  return unit === "point"
    ? `${sign}${value.toFixed(1)}%p`
    : `${sign}${Math.floor(totalMinutes / 60).toLocaleString("ko-KR")}시간 ${totalMinutes % 60}분`;
}

export function evaluateDelta(value: number | null, isIncreaseGood: boolean) {
  if (value === null || value === 0) return "neutral";
  return (value > 0) === isIncreaseGood ? "good" : "danger";
}

export function evaluateRate(value: number) {
  if (value < 30) return "danger";
  if (value < 50) return "warning";
  return "good";
}
