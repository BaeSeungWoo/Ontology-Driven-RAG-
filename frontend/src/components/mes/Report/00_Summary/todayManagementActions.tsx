import type { MesManagementAction } from "@/services/mesApi";
import styles from "../../mes.module.css";

type TodayManagementActionsProps = {
  managementActions: MesManagementAction[];
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

export default function TodayManagementActions({
  managementActions,
  isSummaryLoading,
  summaryErrorMessage,
}: TodayManagementActionsProps) {
  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.insightSection}`}
      aria-label="오늘의 경영 Action"
    >
      <div className={styles.insightHeading}>
        <h3><i data-tone="action" aria-hidden="true" />오늘의 경영 Action</h3>
        <span>권고안</span>
      </div>
      {isSummaryLoading && <p className={styles.reportMessage}>경영 조치를 도출하는 중입니다.</p>}
      {!isSummaryLoading && !summaryErrorMessage && managementActions.length > 0 && (
        <div className={styles.actionGrid}>
          {managementActions.map((action, index) => (
            <article key={`${action.title}-${index}`} className={styles.insightCard}>
              <b className={styles.actionPriority} data-priority={action.priority.slice(0, 2)}>{action.priority}</b>
              <div><strong>{action.title}</strong><p>{action.description}</p></div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
