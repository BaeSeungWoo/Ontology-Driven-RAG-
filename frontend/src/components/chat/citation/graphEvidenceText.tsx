import type { ManualSource } from "@/services/explanationApi";
import styles from "./knowledgeGraphPanel.module.css";
import answerStyles from "../answer/answer.module.css";
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
  function citationBadge(index: number, key: number) {
    const source = sources.find(item => item.index === index);
    const label = `근거 ${index}`;
    const className = `${styles.sourceButton} ${answerStyles.citationLink} ${selected === index ? answerStyles.citationLinkActive : ""}`;
    return source?.node_id
      ? <button key={key} type="button" className={className} aria-label={label} title={label}
          aria-pressed={selected === index} onClick={() => onSelect(source)}>{index}</button>
      : <span key={key} className={className} title={label}>{index}</span>;
  }
  const sentences = (body: string, groupSelected = false) => body.split(/\r?\n/).flatMap(line => {
    const citation = line.match(/^\s*“(.+)”\s*((?:\[근거\s+\d+\]\s*)+)$/);
    const indices = citation ? Array.from(citation[2].matchAll(references), match => Number(match[1])) : [];
    const source = sources.find(item => item.index === indices[0]);
    const rows = source?.rows;
    if (citation && source && rows?.length) {
      const normalize = (value: string) => value.replace(/\s+/g, " ").trim();
      const matches = rows.slice(1).filter(row =>
        row.some(cell => normalize(cell.text) === normalize(citation[1])) ||
        (citation[1].includes("|") && normalize(row.map(cell => cell.text).join(" | ")).includes(normalize(citation[1]))));
      if (matches.length === 1) {
        // A vertically merged cell may start above the cited row.
        const shown = rows.some(row => row.some(cell => (cell.rowspan ?? 1) > 1)) ? rows : [rows[0], matches[0]];
        return [<div key={line} className={selected !== null && indices.includes(selected) ? styles.selectedClaim : undefined}>
          <ManualSourceTable rows={shown} label={`근거 ${source.index} 인용 표`} />
          {indices.map(citationBadge)}
        </div>];
      }
    }
    return evidenceSentences(line).map((sentence, i) => {
    const parts = sentence.split(references);
    const highlighted = groupSelected || parts.some((part, j) => j % 2 === 1 && Number(part) === selected);
    return <p key={line + i} className={highlighted ? styles.selectedClaim : undefined}>
      {parts.map((part, j) => {
        if (j % 2 === 0) return part.split(/(\*\*[^*]+\*\*)/g).map((text, k) =>
          text.startsWith("**") && text.endsWith("**") ? <strong key={k}>{text.slice(2, -2)}</strong> : text);
        return citationBadge(Number(part), j);
      })}
    </p>;
    });
  });
  function actionContent(body: string) {
    // The final citation in a run of steps and signals applies back to the previous citation.
    const lines = body.split("\n");
    let selectedRun = false;
    const highlighted = lines.map(() => false);
    for (let i = lines.length - 1; i >= 0; i--) {
      if (!/^(?:\d+\. |\*\*관련 신호\*\*)/.test(lines[i])) {
        selectedRun = false;
        continue;
      }
      const refs = Array.from(lines[i].matchAll(references), match => Number(match[1]));
      if (refs.length) selectedRun = selected !== null && refs.includes(selected);
      highlighted[i] = selectedRun;
    }

    const content = [];
    for (let i = 0; i < lines.length; i++) {
      if (/^\d+\. /.test(lines[i])) {
        const start = i;
        const steps = [];
        do {
          steps.push(<li key={i}>{sentences(lines[i].replace(/^\d+\. /, ""), highlighted[i])}</li>);
          i++;
        } while (i < lines.length && /^\d+\. /.test(lines[i]));
        content.push(<ol key={start} className={styles.actionSteps}>{steps}</ol>);
        i--;
      } else {
        content.push(<div key={i}>{sentences(lines[i], highlighted[i])}</div>);
      }
    }
    return content;
  }
  return <>{answer.split(/\r?\n\s*\r?\n/).map((block, i) => {
    const card = /^> \[!(SUMMARY|ACTION)\] ([^\n]+)\n([\s\S]*)$/.exec(block);
    if (!card) return <div key={i}>{sentences(block)}</div>;
    const body = card[3].replace(/^> ?/gm, "");
    const content = card[1] === "ACTION" ? actionContent(body) : sentences(body);
    return <AnswerCallout key={i} title={card[2]} kind={card[1] === "ACTION" ? "action" : "summary"}
      isGenerating={busy}>{content}</AnswerCallout>;
  })}</>;
}
