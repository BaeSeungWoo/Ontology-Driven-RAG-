"use client";

import { useState } from "react";
import { type CmsViewKey, type CmsViewRow } from "@/services/cmsApi";
import styles from "../cms.module.css";

type CmsViewTableProps = {
  viewKey: CmsViewKey;
  title: string;
  rows: CmsViewRow[] | null;
  isLoading: boolean;
  errorMessage: string;
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export default function CmsViewTable({
  viewKey,
  title,
  rows,
  isLoading,
  errorMessage,
}: CmsViewTableProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const columns = rows && rows.length > 0 ? Object.keys(rows[0]) : [];
  const contentId = `cms-view-${viewKey}`;

  return (
    <section className={styles.panel}>
      <div className={styles.heading}>
        <div>
          <h2>
            <button
              type="button"
              className={styles.titleButton}
              aria-expanded={isExpanded}
              aria-controls={contentId}
              onClick={() => setIsExpanded((expanded) => !expanded)}
            >
              {title} <span aria-hidden="true">{isExpanded ? "−" : "+"}</span>
            </button>
          </h2>
        </div>
        {rows && !errorMessage && <span>{rows.length}건</span>}
      </div>

      {isExpanded && (
        <div id={contentId}>
          {isLoading && <p className={styles.message}>데이터를 불러오는 중입니다.</p>}
          {errorMessage && <p className={styles.error}>{errorMessage}</p>}
          {!isLoading && !errorMessage && rows?.length === 0 && (
            <p className={styles.message}>조회된 데이터가 없습니다.</p>
          )}
          {!isLoading && !errorMessage && rows === null && (
            <p className={styles.message}>조회된 데이터가 없습니다.</p>
          )}
          {!isLoading && !errorMessage && rows && rows.length > 0 && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column}>{column}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, rowIndex) => (
                    <tr key={rowIndex}>
                      {columns.map((column) => (
                        <td key={column}>{formatValue(row[column])}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
