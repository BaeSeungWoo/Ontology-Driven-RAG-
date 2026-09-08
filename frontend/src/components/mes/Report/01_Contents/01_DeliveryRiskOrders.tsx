import type { MesViewRow } from "@/services/mesApi";
import styles from "../../mes.module.css";
import { formatNumber, toNumber } from "../reportUtils";

/* ===================================================== */

const MAX_ROWS_PER_RISK = 5;

type DeliveryRiskOrdersProps = {
  cardRows: MesViewRow[];
  detailRows: MesViewRow[];
  isLoading: boolean;
  errorMessage: string;
  managementPoint: string;
  isSummaryLoading: boolean;
  summaryErrorMessage: string;
};

/* ===================================================== */

function formatDate(value: unknown): string {
  const date = String(value ?? "");
  return /^\d{4}-\d{2}-\d{2}/.test(date) ? date.slice(0, 10) : date || "-";
}

function formatOrderNumber(row: MesViewRow): string {
  return `${String(row.ORDER_ID ?? "-")}-${String(row.ORDER_SEQ ?? "-")}`;
}

function formatRemainingDays(value: unknown): string {
  const remainingDays = toNumber(value);
  if (remainingDays < 0) return `+${Math.abs(remainingDays)}일`;
  if (remainingDays === 0) return "D-DAY";
  return `D-${remainingDays}`;
}

function getRiskTone(value: unknown): "overdue" | "danger" | "watch" {
  const remainingDays = toNumber(value);
  if (remainingDays < 0) return "overdue";
  if (remainingDays <= 7) return "danger";
  return "watch";
}

function formatProcessSequence(value: unknown): string {
  const sequence = String(value ?? "").trim();
  if (!sequence) return "-";
  return /^\d+$/.test(sequence) ? sequence.padStart(3, "0") : sequence;
}

function getProgressTone(
  completedProcessCount: number,
  totalProcessCount: number,
): "not-started" | "early" | "progress" | "near-complete" {
  if (completedProcessCount === 0 || totalProcessCount === 0) return "not-started";

  const progress = completedProcessCount / totalProcessCount;
  if (progress >= 0.8) return "near-complete";
  if (progress >= 0.5) return "progress";
  return "early";
}

/* ===================================================== */

export default function DeliveryRiskOrders({
  cardRows,
  detailRows,
  isLoading,
  errorMessage,
  managementPoint,
  isSummaryLoading,
  summaryErrorMessage,
}: DeliveryRiskOrdersProps) {
  const card = cardRows[0];
  const sortedRows = [...detailRows]
    .sort((left, right) => toNumber(left.REMAINING_DAYS) - toNumber(right.REMAINING_DAYS));
  const overdueRows = sortedRows
    .filter((row) => toNumber(row.REMAINING_DAYS) < 0)
    .slice(0, MAX_ROWS_PER_RISK);
  const dangerRows = sortedRows
    .filter((row) => {
      const remainingDays = toNumber(row.REMAINING_DAYS);
      return remainingDays >= 0 && remainingDays <= 7;
    })
    .slice(0, MAX_ROWS_PER_RISK);
  const rows = [...dangerRows, ...overdueRows];

  return (
    <section
      className={`${styles.reportSection} ${styles.reportSectionWide} ${styles.deliveryRiskOrdersSection}`}
      aria-label="납기 임박 미완료 수주"
    >
      <header className={styles.deliveryRiskOrdersHeader}>
        <h3>납기 임박 미완료 수주</h3>
        <span>
          총 {formatNumber(card?.TOTAL_RISK_COUNT)}건 · 납기 임박(7일 이내) {dangerRows.length}건 · 납기 경과(최대 30일) {overdueRows.length}건 표시
        </span>
      </header>

      <div className={styles.deliveryRiskBuckets}>
        <article data-tone="danger">
          <span>납기 임박(7일 이내)</span>
          <p><strong>{formatNumber(card?.DUE_WITHIN_7_COUNT)}</strong>건 · 위험</p>
        </article>
        <article data-tone="overdue">
          <span>납기 경과(최대 30일)</span>
          <p><strong>{formatNumber(card?.OVERDUE_COUNT)}</strong>건 · 긴급</p>
        </article>
        <article data-tone="watch">
          <span>8~30일 이내</span>
          <p><strong>{formatNumber(card?.DUE_WITHIN_8_TO_30_COUNT)}</strong>건 · 주의</p>
        </article>
      </div>

      {/* loading */}
      {isLoading && <p className={styles.reportMessage}>납기 임박 수주를 불러오는 중입니다.</p>}
      {!isLoading && errorMessage && <p className={styles.reportError}>{errorMessage}</p>}
      {!isLoading && !errorMessage && rows.length === 0 && (
        <p className={styles.reportMessage}>조회된 납기 임박 미완료 수주가 없습니다.</p>
      )}

      {/* Contents */}
      {!isLoading && !errorMessage && rows.length > 0 && (
        <div className={styles.deliveryRiskOrdersTableWrap}>
          <table className={styles.deliveryRiskOrdersTable}>
            <colgroup>
              <col className={styles.deliveryRiskRemainingColumn} />
              <col className={styles.deliveryRiskOrderColumn} />
              <col className={styles.deliveryRiskCustomerColumn} />
              <col className={styles.deliveryRiskDateColumn} />
              <col className={styles.deliveryRiskProgressColumn} />
              <col className={styles.deliveryRiskNoteColumn} />
            </colgroup>

            <thead>
              <tr>
                <th>잔여</th>
                <th>수주 · 품목</th>
                <th>거래처</th>
                <th>납기</th>
                <th>공정 진척</th>
                <th>비고</th>
              </tr>
            </thead>

            <tbody>
              {rows.map((row, index) => {
                const totalProcessCount = toNumber(row.TOTAL_PROCESS_COUNT);
                const completedProcessCount = toNumber(row.COMPLETED_PROCESS_COUNT);
                const progress = totalProcessCount > 0
                  ? Math.min(100, Math.max(0, completedProcessCount / totalProcessCount * 100))
                  : 0;
                const tone = getRiskTone(row.REMAINING_DAYS);
                const progressTone = getProgressTone(completedProcessCount, totalProcessCount);
                const firstIncompleteProcess = formatProcessSequence(row.FIRST_INCOMPLETE_PROCESS);
                const itemName = String(row.ITEM_NM ?? row.ITEM_CD ?? "-");
                const customerName = String(row.CUST_NM ?? row.CUST_CD ?? "-");
                const processName = String(row.FIRST_INCOMPLETE_PROCESS_NM ?? "").trim();
                const incompleteProcess = processName
                  ? `${processName}${firstIncompleteProcess === "-" ? "" : `(${firstIncompleteProcess})`}부터 미완료`
                  : firstIncompleteProcess === "-"
                    ? "미완료 공정 확인 필요"
                    : `${firstIncompleteProcess}부터 미완료`;

                return (
                  <tr key={`${row.ORDER_ID ?? "order"}-${row.ORDER_SEQ ?? index}-${row.ITEM_CD ?? index}`}>
                    <td>
                      <span className={styles.deliveryRiskDayBadge} data-tone={tone}>
                        {formatRemainingDays(row.REMAINING_DAYS)}
                      </span>
                    </td>
                    <td>
                      <strong>{formatOrderNumber(row)}</strong>
                      <small title={itemName}>{itemName}</small>
                    </td>
                    <td title={customerName}>{customerName}</td>
                    <td>{formatDate(row.DELIVERY_DATE)}</td>
                    <td>
                      <div className={styles.deliveryRiskProgressCell}>
                        <div className={styles.deliveryRiskProgress}>
                          <i data-progress-tone={progressTone} style={{ width: `${progress}%` }} />
                        </div>
                        <small>{formatNumber(completedProcessCount)}/{formatNumber(totalProcessCount)}</small>
                      </div>
                    </td>
                    <td title={incompleteProcess}>{incompleteProcess}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      
      <article className={styles.managementPoint} data-tone="warn">
        <b>경영 포인트</b>
        {isSummaryLoading && <span>납기 리스크를 분석하는 중입니다.</span>}
        {!isSummaryLoading && summaryErrorMessage && <span>{summaryErrorMessage}</span>}
        {!isSummaryLoading && !summaryErrorMessage && managementPoint && (
          <span>{managementPoint}</span>
        )}
      </article>
    </section>
  );
}
