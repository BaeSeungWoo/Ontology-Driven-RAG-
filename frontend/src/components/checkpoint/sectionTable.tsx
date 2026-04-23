"use client";

import { isValidElement, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import styles from "./checkpoint.module.css";

export type TableColumn<T> = {
  header: string;
  render: (row: T) => ReactNode;
  align?: "left" | "center" | "right";
};

type SectionTableProps<T> = {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string;
  emptyText?: string;
  pageSize?: number;
};

// 공통 테이블 셀 포맷
// - number: 천 단위 콤마
// - ReactElement: 그대로 렌더
// - object: 디버깅 가능한 문자열로 변환
function formatTableCellValue(value: ReactNode): ReactNode {
  if (typeof value === "number" && Number.isFinite(value)) {
    return new Intl.NumberFormat("ko-KR").format(value);
  }
  if (isValidElement(value)) {
    return value;
  }
  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value);
    } catch {
      return String(value);
    }
  }
  return value;
}

// align 미지정 시 숫자는 right, 그 외는 left를 기본값으로 사용한다.
function inferAlignFromValue(value: ReactNode): "left" | "right" {
  return typeof value === "number" && Number.isFinite(value) ? "right" : "left";
}

function toAlignClass(
  align: "left" | "center" | "right",
  stylesObj: Record<string, string>
): string {
  if (align === "center") return stylesObj.alignCenter;
  if (align === "right") return stylesObj.alignRight;
  return stylesObj.alignLeft;
}

export default function SectionTable<T>({
  columns,
  rows,
  rowKey,
  emptyText = "데이터 없음",
  pageSize = 8,
}: SectionTableProps<T>) {
  // pageSize는 최소 1 이상으로 강제한다.
  const safePageSize = Math.max(1, pageSize);
  const totalPages = Math.max(1, Math.ceil(rows.length / safePageSize));
  const [currentPage, setCurrentPage] = useState(1);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const pageStartIndex = (currentPage - 1) * safePageSize;
  const pagedRows = useMemo(
    () => rows.slice(pageStartIndex, pageStartIndex + safePageSize),
    [rows, pageStartIndex, safePageSize]
  );

  const pageNumbers = useMemo(
    () => Array.from({ length: totalPages }, (_, index) => index + 1),
    [totalPages]
  );

  const showPagination = rows.length > safePageSize;
  // 마지막 페이지에서 행 수가 부족하면 filler row를 채워 테이블 높이를 고정한다.
  const fillerRowCount =
    showPagination && pagedRows.length < safePageSize
      ? safePageSize - pagedRows.length
      : 0;
  // 헤더 정렬도 셀 정렬 규칙과 동일하게 자동 추론한다.
  const inferredHeaderAligns = useMemo(
    () =>
      columns.map((column) => {
        if (column.align) return column.align;
        for (const row of rows) {
          const rendered = column.render(row);
          if (rendered !== null && rendered !== undefined && rendered !== "") {
            return inferAlignFromValue(rendered);
          }
        }
        return "left";
      }),
    [columns, rows]
  );

  return (
    <div className={styles.tableSection}>
      <div className={styles.tableWrap}>
        <table className={styles.simpleTable}>
          <thead>
            <tr>
              {columns.map((column, index) => (
                <th
                  key={`table-head-${index}`}
                  className={toAlignClass(inferredHeaderAligns[index], styles)}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className={styles.emptyCell}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              <>
                {pagedRows.map((row, index) => {
                  const absoluteIndex = pageStartIndex + index;
                  return (
                    <tr key={rowKey(row, absoluteIndex)}>
                      {columns.map((column, colIndex) => {
                        const rendered = column.render(row);
                        const cellAlign = column.align ?? inferAlignFromValue(rendered);
                        return (
                          <td
                            key={`table-cell-${absoluteIndex}-${colIndex}`}
                            className={toAlignClass(cellAlign, styles)}
                          >
                            {formatTableCellValue(rendered)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
                {Array.from({ length: fillerRowCount }, (_, fillerIndex) => (
                  <tr key={`filler-row-${currentPage}-${fillerIndex}`} aria-hidden="true">
                    {columns.map((_, colIndex) => (
                      <td key={`filler-cell-${currentPage}-${fillerIndex}-${colIndex}`} className={`${styles.tableFillerCell} ${styles.alignLeft}`}>
                        &nbsp;
                      </td>
                    ))}
                  </tr>
                ))}
              </>
            )}
          </tbody>
        </table>
      </div>

      {showPagination ? (
        <div className={styles.tablePager}>
          <button
            type="button"
            className={styles.pagerButton}
            onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
            disabled={currentPage === 1}
          >
            이전
          </button>

          <div className={styles.pagerNumbers}>
            {pageNumbers.map((pageNo) => (
              <button
                key={`page-${pageNo}`}
                type="button"
                className={`${styles.pagerNumber} ${
                  pageNo === currentPage ? styles.pagerNumberActive : ""
                }`}
                onClick={() => setCurrentPage(pageNo)}
              >
                {pageNo}
              </button>
            ))}
          </div>

          <button
            type="button"
            className={styles.pagerButton}
            onClick={() => setCurrentPage((prev) => Math.min(totalPages, prev + 1))}
            disabled={currentPage === totalPages}
          >
            다음
          </button>
        </div>
      ) : null}
    </div>
  );
}
