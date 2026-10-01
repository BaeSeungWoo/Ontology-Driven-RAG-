import type { Root, RootContent, Paragraph, Blockquote } from "mdast";

const labels: Record<string, "summary" | "action"> = {
  "핵심 요약": "summary",
  "핵심 답변": "summary",
  "권장 조치": "action",
  "관리 관점 권고 액션": "action",
};

function textOf(node: { value?: string; children?: unknown[] }): string {
  return node.value ?? (node.children ?? []).map(child => textOf(child as Parameters<typeof textOf>[0])).join("");
}

function sectionLabel(node: RootContent) {
  if (node.type === "heading") return { title: textOf(node).trim().replace(/[:：]$/, ""), body: [] };
  if (node.type !== "paragraph") return null;
  const children = node.children.filter(child => child.type !== "text" || child.value.trim());
  if (children[0]?.type === "strong") {
    const title = textOf(children[0]).trim().replace(/[:：]$/, "");
    const body = children.slice(1);
    if (body[0]?.type === "text") body[0] = { ...body[0], value: body[0].value.replace(/^\s*[:：]?\s*/, "") };
    const content = body.filter(child => child.type !== "text" || child.value.trim());
    if (labels[title] || content.length === 0) return { title, body: content };
  }
  const title = textOf(node).trim().replace(/[:：]$/, "");
  return labels[title] || title === "근거" ? { title, body: [] } : null;
}

function explicitSnippet(node: RootContent): Blockquote | null {
  if (node.type !== "blockquote" || node.children[0]?.type !== "paragraph") return null;
  const [first, ...rest] = node.children;
  const children = first.children.filter(child => child.type !== "text" || child.value.length);
  const marker = children[0];
  if (marker?.type !== "text") return null;
  const match = marker.value.match(/^\[!(SUMMARY|ACTION)\][ \t]*([^\n]*)(?:\n|$)/);
  if (!match) return null;
  const kind = match[1] === "ACTION" ? "action" : "summary";
  const title = match[2].trim() || (kind === "action" ? "실행 안내" : "핵심 내용");
  const body = [{ ...marker, value: marker.value.slice(match[0].length) }, ...children.slice(1)];
  return {
    ...node,
    data: { hName: "section", hProperties: { "data-callout-kind": kind, "data-callout-title": title } },
    children: [
      ...(body.some(child => child.type !== "text" || child.value.trim()) ? [{ ...first, children: body }] : []),
      ...rest,
    ],
  };
}

export default function remarkAnswerCallouts() {
  return (tree: Root) => {
    const snippets = tree.children.map(explicitSnippet);
    if (snippets.some(Boolean)) {
      // Explicit model-selected snippets take precedence over legacy title matching.
      tree.children = tree.children.map((node, index) => snippets[index] ?? node);
      return;
    }
    // Older answers have no markers, so retain their title-based presentation.
    const result: RootContent[] = [];
    let active: Blockquote | null = null;
    for (const node of tree.children) {
      const label = sectionLabel(node);
      const kind = label && labels[label.title];
      const citationOnly = node.type === "paragraph" && node.children.every(child =>
        (child.type === "text" && !child.value.trim()) ||
        (child.type === "link" && /^#chunk-\d+$/.test(child.url))
      );
      if (label || node.type === "thematicBreak" || citationOnly) active = null;
      if (label && kind) {
        const card: Blockquote = {
          type: "blockquote",
          data: { hName: "section", hProperties: { "data-callout-kind": kind, "data-callout-title": label.title } },
          children: label.body.length ? [{ type: "paragraph", children: label.body } as Paragraph] : [],
        };
        result.push(card);
        // Inline labels apply to their paragraph; standalone labels also own following blocks.
        if (!label.body.length) active = card;
      } else if (active) {
        active.children.push(node as Blockquote["children"][number]);
      } else {
        result.push(node);
      }
    }
    tree.children = result;
  };
}
