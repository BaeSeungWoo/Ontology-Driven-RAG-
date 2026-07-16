import type { ChatChunk, MessageItem } from "@/types/chatApi";

export type SelectedCitation = {
  messageId: string;
  chunkIndex: number;
} | null;

export type CitationDocumentRequest = {
  documentKey: string;
  sourceDocName: string;
  pageRange: string | null;
  pageLabel: string | null;
  chunkText: string;
  referenceLabel: string;
};

export function getLatestAssistantMessage(messages: MessageItem[]): MessageItem | undefined {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === "assistant" && message.metadata) return message;
  }
  return undefined;
}

export function getActiveMessage(
  messages: MessageItem[],
  activeAssistantMessageId?: string | null
): MessageItem | undefined {
  if (activeAssistantMessageId) {
    const activeMessage = messages.find(
      (message) =>
        message.role === "assistant" &&
        String(message.message_id) === activeAssistantMessageId
    );
    if (activeMessage) return activeMessage;
  }

  return getLatestAssistantMessage(messages);
}

export function getSelectedMessage(
  messages: MessageItem[],
  selectedCitation?: SelectedCitation
): MessageItem | undefined {
  if (!selectedCitation) return undefined;
  return messages.find(
    (message) => String(message.message_id) === selectedCitation.messageId
  );
}

export function getSelectedChunk(
  messages: MessageItem[],
  selectedCitation?: SelectedCitation
): ChatChunk | undefined {
  const message = getSelectedMessage(messages, selectedCitation);
  const chunks = message?.metadata?.chunks ?? [];
  return chunks.find((chunk) => chunk.index === selectedCitation?.chunkIndex);
}

export function getReferenceLabelMap(answerText = "") {
  const labelMap = new Map<number, number>();
  const citationPattern = /\[(?:chunk:)?(\d+)\]/gi;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(answerText)) !== null) {
    const chunkIndex = Number(match[1]);
    if (!labelMap.has(chunkIndex)) {
      labelMap.set(chunkIndex, labelMap.size + 1);
    }
  }

  return labelMap;
}

export function getReferenceItems(answerText = "") {
  return Array.from(getReferenceLabelMap(answerText).entries())
    .map(([chunkIndex, label]) => ({ chunkIndex, label }))
    .sort((left, right) => left.label - right.label);
}

function toPageLabel(range: unknown): string | null {
  if (typeof range !== "string") return null;
  const normalized = range.trim();
  if (!normalized) return null;

  const rangeMatch = normalized.match(/^(\d+)\s*-\s*(\d+)$/);
  if (rangeMatch) {
    const [, start, end] = rangeMatch;
    return start === end ? `p.${start}` : `p.${start}~p.${end}`;
  }

  return /^\d+$/.test(normalized)
    ? `p.${normalized}`
    : `p.${normalized.replace(/\s*-\s*/g, "~")}`;
}

export function getChunkPageRange(chunk?: ChatChunk): string | null {
  const pageRange = typeof chunk?.metadata?.page_range === "string" ? chunk.metadata.page_range : null;
  if (pageRange) return pageRange;

  const pages = chunk?.metadata?.pages;
  if (pages && typeof pages === "object" && "range" in pages && typeof pages.range === "string") {
    return pages.range;
  }

  return null;
}

export function getChunkPageLabel(chunk?: ChatChunk): string | null {
  return toPageLabel(getChunkPageRange(chunk));
}

export function getCitationDocumentRequest(
  messages: MessageItem[],
  selectedCitation?: SelectedCitation,
  activeAssistantMessageId?: string | null
): CitationDocumentRequest | null {
  if (!selectedCitation) return null;

  const activeMessage = getActiveMessage(messages, activeAssistantMessageId);
  const selectedMessage = getSelectedMessage(messages, selectedCitation);
  const selectedChunk = getSelectedChunk(messages, selectedCitation);
  const sourceDocName =
    typeof selectedChunk?.metadata?.source_doc_name === "string"
      ? selectedChunk.metadata.source_doc_name
      : null;

  if (!selectedChunk || !sourceDocName) return null;

  const pageRange = getChunkPageRange(selectedChunk);
  const referenceLabelMap = getReferenceLabelMap(selectedMessage?.content ?? activeMessage?.content ?? "");
  const referenceLabel = referenceLabelMap.has(selectedCitation.chunkIndex)
    ? `참조${referenceLabelMap.get(selectedCitation.chunkIndex)}`
    : `참조${selectedCitation.chunkIndex}`;

  return {
    documentKey: `${selectedCitation.messageId}:${selectedCitation.chunkIndex}:${sourceDocName}:${pageRange ?? ""}`,
    sourceDocName,
    pageRange,
    pageLabel: getChunkPageLabel(selectedChunk),
    chunkText: selectedChunk.document,
    referenceLabel,
  };
}

export function formatJson(value?: unknown) {
  if (value === undefined) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
