import type { DailySummaryApi } from "@/types/dailyReport";
import styles from "../dailyReport.module.css";
import SectionHeading from "../sectionHeading";

type SummarySectionProps = {
  summary?: DailySummaryApi;
  isLoading?: boolean;
};

export default function SummarySection({ summary, isLoading = false }: SummarySectionProps) {
  const title = isLoading ? "요약 생성 중..." : "출근 즉시 확인하는 전일 운영 요약";
  const body = summary?.text ?? "전일 데이터 요약이 준비되면 이 영역에 표시됩니다.";

  return (
    <div>
      <SectionHeading idx="01 / 전일 종합 요약" title="Executive" emphasize="Summary" />
      <div className={styles.summaryHero}>
        <div className={styles.summaryTag}>AI Generated</div>
        <h3 className={styles.summaryTitle}>{title}</h3>
        <p className={styles.summaryBody}>{body}</p>
      </div>
    </div>
  );
}
