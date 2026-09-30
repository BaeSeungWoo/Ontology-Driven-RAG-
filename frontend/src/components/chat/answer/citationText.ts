const CITATION_PATTERN = /\[(?:chunk:)?(\d+)\]/gi;

function createCitationLabeler() {
  const labelMap = new Map<number, number>();

  return (chunkIndex: number) => {
    if (!labelMap.has(chunkIndex)) {
      labelMap.set(chunkIndex, labelMap.size + 1);
    }

    return `[${labelMap.get(chunkIndex)}](#chunk-${chunkIndex})`;
  };
}

export function toCitationDisplayText(text: string) {
  const getCitationLabel = createCitationLabeler();

  const chunkIndexes: number[] = [];
  const withoutInlineCitations = text.replace(
    CITATION_PATTERN,
    (_match, chunkIndexText: string) => {
      const chunkIndex = Number(chunkIndexText);
      if (!chunkIndexes.includes(chunkIndex)) {
        chunkIndexes.push(chunkIndex);
      }
      return "";
    }
  );

  if (chunkIndexes.length === 0) return text;

  const citationText = chunkIndexes.map(getCitationLabel).join(" ");
  return `${withoutInlineCitations.trimEnd()}\n\n${citationText}`;
}
