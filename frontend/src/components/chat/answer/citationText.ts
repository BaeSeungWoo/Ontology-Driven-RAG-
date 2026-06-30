const CITATION_PATTERN = /\[(?:chunk:)?(\d+)\]/gi;
const CITATION_LABEL_PREFIX = "참조";

function createCitationLabeler() {
  const labelMap = new Map<number, number>();

  return (chunkIndex: number) => {
    if (!labelMap.has(chunkIndex)) {
      labelMap.set(chunkIndex, labelMap.size + 1);
    }

    return `[${CITATION_LABEL_PREFIX}${labelMap.get(chunkIndex)}](#chunk-${chunkIndex})`;
  };
}

export function toCitationDisplayText(text: string) {
  const getCitationLabel = createCitationLabeler();

  return text
    .split(/(\n\s*\n)/)
    .map((part) => {
      if (/^\n\s*\n$/.test(part)) return part;

      const chunkIndexes: number[] = [];
      const withoutInlineCitations = part.replace(
        CITATION_PATTERN,
        (_match, chunkIndexText: string) => {
          const chunkIndex = Number(chunkIndexText);
          if (!chunkIndexes.includes(chunkIndex)) {
            chunkIndexes.push(chunkIndex);
          }
          return "";
        }
      );

      if (chunkIndexes.length === 0) return withoutInlineCitations;

      const citationText = chunkIndexes.map(getCitationLabel).join(" ");
      return `${withoutInlineCitations.trimEnd()} ${citationText}`;
    })
    .join("");
}
