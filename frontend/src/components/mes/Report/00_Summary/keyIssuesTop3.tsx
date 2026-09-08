import type { MesKeyIssue } from "@/services/mesApi";
import styles from "../../mes.module.css";

type KeyIssuesTop3Props = {
  keyIssues: MesKeyIssue[];
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

export default function KeyIssuesTop3({
  keyIssues,
  isSummaryLoading,
  summaryErrorMessage,
}: KeyIssuesTop3Props) {
  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.insightSection}`}
      aria-label="핵심 이슈 TOP 3"
    >
      <div className={styles.insightHeading}>
        <h3><i data-tone="issue" aria-hidden="true" />핵심 이슈 TOP 3</h3>
        <span>LLM 요약</span>
      </div>

      {/* loading */}
      {isSummaryLoading && <p className={styles.reportMessage}>핵심 이슈를 분석하는 중입니다.</p>}

      {!isSummaryLoading && !summaryErrorMessage && keyIssues.length > 0 && (
        <div className={styles.issueGrid}>
          {keyIssues.map((issue, index) => (
            <article key={`${issue.title}-${index}`} className={styles.insightCard}>
              <b className={styles.issueRank}>{index + 1}</b>
              <div><strong>{issue.title}</strong><p>{issue.description}</p></div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
