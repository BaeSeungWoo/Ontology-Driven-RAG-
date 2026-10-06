import { BellRing, ChartNoAxesCombined, Clock3, Sparkles } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import type { CmsReport } from "@/services/cmsApi";
import styles from "../../cms.module.css";

const summaryDefinitions: Array<{ label: string; icon: LucideIcon }> = [
  { label: "계획가동률", icon: ChartNoAxesCombined },
  { label: "시간별 가동률", icon: Clock3 },
  { label: "알람", icon: BellRing },
];

function buildSummaryItems(summary: string) {
  const lines = summary
    .split("\n")
    .map((line) => line.replace(/^[•\-\s]+/, "").trim())
    .filter(Boolean);
  const items = summaryDefinitions.map((definition) => {
    const line = lines.find((value) => value.startsWith(`${definition.label}:`));
    return line ? { ...definition, text: line.slice(definition.label.length + 1).trim() } : null;
  });

  return items.every((item): item is { label: string; icon: LucideIcon; text: string } => item !== null)
    ? items
    : null;
}

export default function CmsReportSummary({ report, isLoading, errorMessage }: { report: CmsReport; isLoading: boolean; errorMessage: string }) {
  const summaryItems = buildSummaryItems(report.executiveSummary);

  return (
    <section className={styles.executiveSummary}>
      <div className={styles.summaryTitle}>
        <span className={styles.summaryLeadIcon}><Sparkles aria-hidden="true" /></span>
        <h3>운영 상황 요약</h3>
        <span className={styles[`evaluation_${report.evaluation.status}`]}>{report.evaluation.label}</span>
      </div>
      {isLoading ? (
        <p role="status">AI 운영 요약을 생성하고 있습니다. 아래 데이터는 먼저 확인할 수 있습니다.</p>
      ) : errorMessage ? (
        <p role="alert">{errorMessage}</p>
      ) : summaryItems ? (
        <ul className={styles.summaryInsightList}>
          {summaryItems.map(({ label, icon: Icon, text }) => (
            <li key={label}>
              <span><Icon aria-hidden="true" /></span>
              <p><b>{label}</b>{text}</p>
            </li>
          ))}
        </ul>
      ) : (
        <p>{report.executiveSummary || "요약 결과가 없습니다."}</p>
      )}
    </section>
  );
}
