import styles from "./citation.module.css";
import { formatCmsDateTime } from "@/utils/formatCmsDateTime";

const labels: Record<string, string> = {
  work_date: "테스트 기준일", work_date_from: "시작 작업일", machine_code: "장비 코드",
  machine_name: "장비명", window_start: "조회 시작", window_end_exclusive: "조회 종료 (해당 시각 제외)",
  history_rows: "상태 이력 건수", alarm_events: "전체 알람 발생 건수", alarm_limit: "표시 알람 종류 상한",
  recent_events_per_alarm: "알람별 최근 사례 상한", requested_codes: "질문에서 지정한 알람",
  code: "알람 코드", count: "발생 횟수", last_occurred_at: "최근 발생 시각",
  closed_duration_seconds: "종료 확인 알람 지속시간 합계 (초)",
  unfinished_records_at_cutoff: "기준 시각에 종료 미확인인 기록 수",
  latest_record_before_cutoff: "기준 시각 이전 마지막 상태 기록",
  status: "상태", alarm_code: "알람 코드", occurred_at: "발생 시각", finished_at: "종료 시각",
  details: "알람 내용", duration_seconds: "지속시간 (초)",
  definition_registered: "알람 설명 출처", alarm_name: "알람명", alarm_description: "알람내용",
  planned_seconds: "계획 가동시간 (초)", planned_rate: "계획 대비 가동률 (%)",
  status_seconds: "상태별 시간 (초)", stop: "정지", operate: "가동", alarm: "알람", off: "전원 OFF",
};

export function parseCmsEvidence(text: string): Record<string, unknown> | null {
  try {
    const value = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value) ? value : null;
  } catch { return null; }
}

export function cmsEvidenceSummary(text: string) {
  const data = parseCmsEvidence(text);
  if (!data) return "DB 조회 결과의 상세 내용을 확인하세요.";
  if (data.code !== undefined) return `알람 ${data.code || "코드 미기록"} · 발생 ${data.count ?? "미확인"}건`;
  return [data.machine_name || data.machine_code, data.work_date_from && `${data.work_date_from}부터`,
    data.work_date && `${data.work_date} 기준`, data.alarm_events !== undefined && `알람 ${data.alarm_events}건`]
    .filter(Boolean).join(" · ") || "CMS 장비 운영 집계";
}

export function getAlarmManualDefinition(text: string, code: unknown): { name: string; description: string } | null {
  if (typeof code !== "string" || !code) return null;
  // Match the code column, so adjacent alarms in the same table cannot be substituted.
  for (const line of text.split("\n")) {
    const row = line.match(/\bC0:\s*([^|]+)\|\s*C1:\s*([^|]+)\|\s*C2:\s*(.+)/);
    if (row && row[1].trim().toUpperCase() === code.toUpperCase()) {
      return { name: row[2].trim(), description: row[3].trim() };
    }
  }
  return null;
}

export function getAlarmManualDescription(text: string, code: unknown): string | null {
  const definition = getAlarmManualDefinition(text, code);
  return definition ? `${definition.name} — ${definition.description}` : null;
}

function fields(data: Record<string, unknown>) {
  return <dl className={styles.cmsFields}>{Object.entries(data).map(([key, value]) => {
    if (!labels[key]) return null;
    let display;
    if (key === "definition_registered") display = value ? "등록됨 · TDAA0002_TBL" : data.manual_definition ? "매뉴얼 기준 · 현재 장비" : "설명 없음 · DB 및 연결된 매뉴얼";
    else if (key === "alarm_name" || key === "alarm_description") display = value ? String(value) : (data.definition_registered === false ? "설명 없음" : "미입력");
    else if (value === null || value === undefined) display = "미확인";
    else if (Array.isArray(value)) display = value.length ? value.join(", ") : "없음";
    else if (typeof value === "object") display = fields(value as Record<string, unknown>);
    else if (key === "status") display = ({ "0": "정지", "1": "가동", "2": "알람", "3": "전원 OFF" } as Record<string, string>)[String(value)] ?? "미확인";
    else display = formatCmsDateTime(String(value));
    return <div key={key}><dt>{labels[key]}</dt><dd>{display}</dd></div>;
  })}</dl>;
}

export default function CmsEvidence({ text, manualDescription, manualDefinition }: {
  text: string;
  manualDescription?: string | null;
  manualDefinition?: { name: string; description: string } | null;
}) {
  const data = parseCmsEvidence(text);
  if (!data) return <p>저장된 DB 조회 결과를 표시할 수 없습니다.</p>;
  const events = data.recent_events ?? data.events;
  const displayedData = data.definition_registered === false && manualDefinition
    ? { ...data, manual_definition: true, alarm_name: manualDefinition.name, alarm_description: manualDefinition.description }
    : data;
  return <section className={styles.cmsEvidence} aria-label="DB 조회 근거">
    <p className={styles.cmsNotice}>답변 생성 당시의 CMS 조회 결과입니다. 실시간 상태가 아닙니다.</p>
    {fields(displayedData)}
    {Array.isArray(data.hourly_counts) && data.hourly_counts.length > 0 && <>
      <h4>발생 시간대별 집계</h4>
      <table><thead><tr><th>시간대</th><th>발생 횟수</th></tr></thead><tbody>
        {data.hourly_counts.filter(row => Array.isArray(row) && row.length === 2).map((row, index) =>
          <tr key={index}><td>{String(row[0])}시</td><td>{String(row[1])}건</td></tr>)}
      </tbody></table>
    </>}
    {Array.isArray(data.hourly_rates) && <>
      <h4>시간대별 가동률</h4>
      <table><thead><tr><th>시작 시각</th><th>가동률</th></tr></thead><tbody>
        {data.hourly_rates.filter(row => row && typeof row === "object").map((row, index) =>
          <tr key={index}><td>{formatCmsDateTime(String(row.start ?? "미확인"))}</td><td>{row.rate == null ? "미확인" : `${row.rate}%`}</td></tr>)}
      </tbody></table>
    </>}
    {Array.isArray(events) && events.length > 0 && <>
      <h4>{data.recent_events ? "최근 발생 사례" : "발생 사례"}</h4>
      <ol className={styles.cmsEvents}>{events.filter(event => event && typeof event === "object").map((event, index) => {
        const damaged = typeof event.details === "string" && /\?{2,}|\uFFFD/.test(event.details);
        const axis = damaged ? event.details.match(/^\([A-Z]\)/)?.[0] : null;
        const displayedEvent = damaged ? { ...event, details: manualDescription
          ? `${axis ? `${axis} ` : ""}${manualDescription}`
          : "DB 원문 손상으로 알람 내용을 확인할 수 없습니다." } : event;
        return <li key={index}>{fields(displayedEvent)}
          {damaged && manualDescription && <p className={styles.cmsNotice}>DB 알람 메시지에 대체 문자(?, �)가 있어 현재 장비 매뉴얼의 설명을 표시합니다.</p>}
        </li>;
      })}</ol>
    </>}
  </section>;
}
