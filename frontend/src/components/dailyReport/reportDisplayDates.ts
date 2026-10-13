import { TEST_REPORT_DATE } from "./reportDatePicker";

const DAY_MS = 24 * 60 * 60 * 1000;

// 저장본은 수정하지 않고 시연용 복사본의 날짜만 작성일 전날에 맞춥니다.
export function shiftReportDisplayDates<T>(value: T, displayDate: string): T {
  const offset = Date.parse(`${displayDate}T00:00:00Z`) - DAY_MS
    - Date.parse(`${TEST_REPORT_DATE}T00:00:00Z`);
  const shift = (date: string, adjustment = 0) => new Date(Date.parse(`${date}T00:00:00Z`) + offset + adjustment).toISOString().slice(0, 10);

  const visit = (item: unknown, key = "", adjustment = 0): unknown => {
    if (Array.isArray(item)) {
      if (key === "longestAlarms" || key === "longest-alarm-top3") {
        // 원본 알람에는 집계일 다음 날 기록도 있어, 이력 전체를 같은 일수만큼 앞당깁니다.
        const latest = item.flatMap(row => [row.occurDate, row.finishDate, row.OCCUR_DATE, row.FINISH_DATE])
          .filter((date): date is string => typeof date === "string" && /^\d{4}-\d{2}-\d{2}/.test(date))
          .map(date => date.slice(0, 10)).sort().at(-1);
        if (latest && latest > TEST_REPORT_DATE) {
          adjustment = Date.parse(`${TEST_REPORT_DATE}T00:00:00Z`) - Date.parse(`${latest}T00:00:00Z`);
        }
      }
      return item.map(entry => visit(entry, key, adjustment));
    }
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.entries(item).map(([name, entry]) => [name, visit(entry, name, adjustment)]));
    }
    if (typeof item !== "string") return item;
    // 수주 번호·장비 코드 등 식별자는 날짜처럼 보여도 그대로 둡니다.
    if (!/date|At$|summary|description|point_|label|details/i.test(key)) return item;
    if (key === "label" && /^\d{2}\/\d{2}$/.test(item)) {
      return shift(`${TEST_REPORT_DATE.slice(0, 4)}-${item.replace("/", "-")}`).slice(5).replace("-", "/");
    }
    return item.replace(/\b(\d{4}-\d{2}-\d{2})(?=T|\b)/g, date => shift(date, adjustment));
  };

  return visit(value) as T;
}
