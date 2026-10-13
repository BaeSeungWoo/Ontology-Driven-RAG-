import type { ChatMetadata } from "@/types/chatApi";
import { getReferenceItems } from "../citation/citationUtils";

const CITATION_PATTERN = /\[chunk:(\d+)\]/gi;

export function toCitationDisplayText(text: string, metadata?: ChatMetadata) {
  const references = getReferenceItems(text, metadata);
  const withoutInlineCitations = text.replace(CITATION_PATTERN, "");

  if (references.length === 0) return withoutInlineCitations;

  const citationText = references
    .map(({ chunkIndex, label }) => `[${label}](#chunk-${chunkIndex})`).join(" ");
  return `${withoutInlineCitations.trimEnd()}\n\n${citationText}`;
}
