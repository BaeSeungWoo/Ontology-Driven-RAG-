"use client";

import { useState } from "react";
import { type MesViewRow } from "@/services/mesApi";
import styles from "../mes.module.css";

type MesViewTableProps = {
  viewKey: string;
  title: string;
  rows: MesViewRow[] | null;
  isLoading: boolean;
  errorMessage: string;
  columnLabels?: Record<string, string>;
};

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

export default function MesViewTable({
  viewKey,
  title,
  rows,
  isLoading,
  errorMessage,
  columnLabels = {},
}: MesViewTableProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const columns = rows && rows.length > 0 ? Object.keys(rows[0]) : [];
  const contentId = `mes-view-${viewKey}`;

  return (
    <section className={styles.panel}>
      <div className={styles.heading}>
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
        {rows && !errorMessage && <span>{rows.length}건</span>}
      </div>

      {isExpanded && (
        <div id={contentId}>
          {isLoading && <p className={styles.message}>데이터를 불러오는 중입니다.</p>}
          {errorMessage && <p className={styles.error}>{errorMessage}</p>}
          {!isLoading && !errorMessage && !rows?.length && (
            <p className={styles.message}>조회된 데이터가 없습니다.</p>
          )}
          {!isLoading && !errorMessage && rows && rows.length > 0 && (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={column} scope="col">
                        {column}{columnLabels[column] ? ` (${columnLabels[column]})` : ""}
                      </th>
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
