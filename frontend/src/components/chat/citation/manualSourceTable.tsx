import type { ManualSource } from "@/services/explanationApi";
import styles from "./knowledgeGraphPanel.module.css";

export default function ManualSourceTable({ rows, label }: { rows: NonNullable<ManualSource["rows"]>; label: string }) {
  return <div className={styles.sourceTable}><table aria-label={label}>
    <tbody>{rows.map((row, i) => <tr key={i}>{row.map((cell, col) => i === 0
      ? <th key={col} scope="col" colSpan={cell.colspan} rowSpan={cell.rowspan}>{cell.text}</th>
      : <td key={col} colSpan={cell.colspan} rowSpan={cell.rowspan}>{cell.text}</td>)}</tr>)}</tbody>
  </table></div>;
}
