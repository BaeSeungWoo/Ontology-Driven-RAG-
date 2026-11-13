import type { ManualSource } from "@/services/explanationApi";
import styles from "./knowledgeGraphPanel.module.css";
import AnswerCallout from "../answer/answerCallout";
import ManualSourceTable from "./manualSourceTable";

const references = /\[근거\s+(\d+)\]/g;

// Keep adjacent citations with the preceding sentence, including "문장. [근거 1]".
export function evidenceSentences(answer: string) {
  return answer.split(/\r?\n/).flatMap(line => line.trim().split(
    /(?<=[.!?。])\s+(?!\s|\[근거\s+\d+\])|(?<=\])\s+(?!\s|\[근거\s+\d+\])/u,
  )).filter(Boolean);
}

export default function GraphEvidenceText({ answer, sources, selected, onSelect, busy = false }: {
  answer: string; sources: ManualSource[]; selected: number | null; onSelect: (source: ManualSource) => void; busy?: boolean;
}) {
  const sentences = (body: string) => body.split(/\r?\n/).flatMap(line => {
    const citation = line.match(/^\s*“(.+\|.+)”\s*\[근거\s+(\d+)\]\s*$/);
    const source = citation && sources.find(item => item.index === Number(citation[2]));
    const rows = source?.rows;
    if (citation && source && rows?.length) {
      const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
      const matches = rows.slice(1).filter(row =>
        normalize(row.map(cell => cell.text).join(" | ")).includes(normalize(citation[1])));
      if (matches.length === 1) {
        // A vertically merged cell may start above the cited row.
        const shown = rows.some(row => row.some(cell => (cell.rowspan ?? 1) > 1)) ? rows : [rows[0], matches[0]];
        return [<div key={line} className={selected === source.index ? styles.selectedClaim : undefined}>
          <ManualSourceTable rows={shown} label={`근거 ${source.index} 인용 표`} />
          {source.node_id ? <button type="button" className={styles.sourceButton} aria-pressed={selected === source.index}
            onClick={() => onSelect(source)}>[근거 {source.index}]</button> : `[근거 ${source.index}]`}
        </div>];
      }
    }
    return evidenceSentences(line).map((sentence, i) => {
    const parts = sentence.split(references);
    const highlighted = parts.some((part, j) => j % 2 === 1 && Number(part) === selected);
    return <p key={line + i} className={highlighted ? styles.selectedClaim : undefined}>
      {parts.map((part, j) => {
        if (j % 2 === 0) return part.split(/(\*\*[^*]+\*\*)/g).map((text, k) =>
          text.startsWith("**") && text.endsWith("**") ? <strong key={k}>{text.slice(2, -2)}</strong> : text);
        const source = sources.find(item => item.index === Number(part));
        return source?.node_id ? <button type="button" key={j} className={styles.sourceButton}
          aria-pressed={selected === source.index} onClick={() => onSelect(source)}>[근거 {part}]</button>
          : `[근거 ${part}]`;
      })}
    </p>;
    });
  });
  return <>{answer.split(/\r?\n\s*\r?\n/).map((block, i) => {
    const card = /^> \[!(SUMMARY|ACTION)\] ([^\n]+)\n([\s\S]*)$/.exec(block);
    if (!card) return <div key={i}>{sentences(block)}</div>;
    return <AnswerCallout key={i} title={card[2]} kind={card[1] === "ACTION" ? "action" : "summary"}
      isGenerating={busy}>{sentences(card[3].replace(/^> ?/gm, ""))}</AnswerCallout>;
  })}</>;
}
