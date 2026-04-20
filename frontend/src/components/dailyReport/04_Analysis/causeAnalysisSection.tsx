import type { DailyAnalysisApi } from "@/types/dailyReport";
import styles from "../dailyReport.module.css";
import SectionHeading from "../sectionHeading";

type CauseAnalysisSectionProps = {
  analysis?: DailyAnalysisApi;
  isLoading?: boolean;
};

export default function CauseAnalysisSection({ analysis, isLoading = false }: CauseAnalysisSectionProps) {
  const first = analysis?.[0];
  const causeList = first?.problem.cause ?? [];
  const summary = first?.problem.result.summary ?? "원인 분석 결과가 없습니다.";
  const action = first?.problem.result.action ?? "추천 조치가 없습니다.";

  return (
    <div>
      <SectionHeading
        idx="04 / 원인 분석 · Root Cause"
        title="Cause Analysis &"
        emphasize="Recommendation"
      />
      <section className={styles.causeTree}>
        <p className={styles.causeDesc}>
          단순 경보 나열이 아니라 지표 상관관계를 기준으로 원인 후보를 정리하고 실행 가능한 조치안을
          함께 제시합니다.
        </p>
        <div className={styles.causeLayout}>
          <article className={styles.causeProblem}>
            <p>Problem</p>
            <h3>{isLoading ? "분석 중..." : "핵심 문제"}</h3>
          </article>

          <div className={styles.causeBranches}>
            {isLoading && <div className={styles.branch}><span>로딩 중...</span></div>}
            {!isLoading && causeList.length === 0 && (
              <div className={styles.branch}>
                <span>표시할 원인 데이터가 없습니다.</span>
              </div>
            )}
            {!isLoading &&
              causeList.map((cause, index) => (
                <div className={styles.branch} key={`cause-${index}`}>
                  <span>{cause}</span>
                </div>
              ))}
          </div>

          <article className={styles.causeResult}>
            <p>Final Result</p>
            <div className={styles.resultBlock}>
              <strong>원인 요약</strong>
              <span>{summary}</span>
            </div>
            <div className={styles.resultBlock}>
              <strong>조치 추천</strong>
              <span>{action}</span>
            </div>
          </article>
        </div>
      </section>
    </div>
  );
}
