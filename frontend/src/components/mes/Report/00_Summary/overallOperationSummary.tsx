import styles from "../../mes.module.css";

type OverallOperationSummaryProps = {
  overallSummary: string;
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

export default function OverallOperationSummary({
  overallSummary,
  isSummaryLoading,
  summaryErrorMessage,
}: OverallOperationSummaryProps) {
  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.overallSummaryCard}`}
      aria-label="전체 운영 요약"
    >
      <span className={styles.overallSummaryBadge} aria-hidden="true">AI</span>
      <div className={styles.overallSummaryContent}>
        <h3>전체 운영 요약</h3>
        {isSummaryLoading && <p className={styles.reportMessage}>영역별 답변을 종합하는 중입니다.</p>}
        {!isSummaryLoading && summaryErrorMessage && <p className={styles.reportError}>{summaryErrorMessage}</p>}
        {!isSummaryLoading && !summaryErrorMessage && overallSummary && (
          <p className={styles.overallSummary}>{overallSummary}</p>
        )}
      </div>
    </section>
  );
}
