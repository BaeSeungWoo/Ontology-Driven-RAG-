import type { ChatMetadata } from "@/types/chatApi";
import { getReferenceItems } from "../citation/citationUtils";

const CITATION_PATTERN = /\[chunk:(\d+)\]/gi;

export function toCitationDisplayText(text: string, metadata?: ChatMetadata) {
  const references = getReferenceItems(text, metadata);
  const withoutRecordIntro = text.replace(
    /^([ \t]*(?:>[ \t]*)?(?:[-*][ \t]+|\d+\.[ \t]+)?)(?:\[chunk:\d+\]|해당 기록)[ \t]*에 따르면[ \t]*,?[ \t]*/gim,
    "$1"
  );
  // Keep the noun when a citation is used as part of a Korean sentence.
  const withCitationSubjects = withoutRecordIntro.replace(
    /\[chunk:\d+\][ \t]*(으로|에서|에게|에는|에도|은|는|이|가|을|를|과|와|의|에|도|만|로)(?=\s|$|[,.!?])/gi,
    (_, particle: string) => {
      const particles: Record<string, string> = { 는: "은", 가: "이", 를: "을", 와: "과", 로: "으로" };
      return `해당 기록${particles[particle] ?? particle}`;
    }
  );
  const withoutInlineCitations = withCitationSubjects.replace(CITATION_PATTERN, "");

  if (references.length === 0) return withoutInlineCitations;

  const citationText = references
    .map(({ chunkIndex, label }) => `[${label}](#chunk-${chunkIndex})`).join(" ");
  return `${withoutInlineCitations.trimEnd()}\n\n${citationText}`;
}
