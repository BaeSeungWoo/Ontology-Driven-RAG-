type TextItemLike = {
  str?: string;
};

type TextRange = {
  index: number;
  start: number;
  end: number;
};

function normalizeText(value: unknown) {
  return String(value || "")
    .toLowerCase()
    .replace(/^passage:\s*/i, "")
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201c\u201d]/g, '"')
    .replace(/[^0-9a-z가-힣]+/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function buildPageTextMap(items: TextItemLike[]) {
  let text = "";
  const ranges: TextRange[] = [];

  items.forEach((item, index) => {
    const normalized = normalizeText(item?.str);
    if (!normalized) return;

    if (text) text += " ";
    const start = text.length;
    text += normalized;
    ranges.push({ index, start, end: text.length });
  });

  return { text, ranges };
}

function getSearchWindows(chunkText: string) {
  const normalized = normalizeText(chunkText);
  if (!normalized) return [];

  const words = normalized.split(" ").filter(Boolean);
  const windowSize = Math.min(18, words.length);

  if (words.length <= windowSize) return [normalized];

  const windows: string[] = [];
  const step = Math.max(6, Math.floor(windowSize / 2));
  for (let start = 0; start <= words.length - windowSize; start += step) {
    windows.push(words.slice(start, start + windowSize).join(" "));
  }

  windows.push(words.slice(-windowSize).join(" "));
  return Array.from(new Set(windows));
}

export function findHighlightItemIndexes(items: TextItemLike[], chunkText: string) {
  const { text, ranges } = buildPageTextMap(items);
  if (!text) return [];

  const matchedIndexes = new Set<number>();

  for (const windowText of getSearchWindows(chunkText)) {
    const start = text.indexOf(windowText);
    if (start < 0) continue;

    const end = start + windowText.length;
    ranges
      .filter((range) => range.start < end && range.end > start)
      .forEach((range) => matchedIndexes.add(range.index));
  }

  return Array.from(matchedIndexes).sort((left, right) => left - right);
}
