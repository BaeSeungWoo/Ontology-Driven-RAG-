type MarkdownNode = {
  type: string;
  value?: string;
  children?: MarkdownNode[];
};

const ARROWS: Record<string, string> = {
  rightarrow: "→",
  leftarrow: "←",
  leftrightarrow: "↔",
  Rightarrow: "⇒",
  Leftarrow: "⇐",
  Leftrightarrow: "⇔",
};

// Repair only text left unparsed by Markdown; code and HTML nodes stay untouched.
export default function remarkAnswerFormatting() {
  return function transform(node: MarkdownNode) {
    if (!node.children) return;
    node.children = node.children.flatMap((child): MarkdownNode[] => {
      if (child.type !== "text" || child.value === undefined) {
        transform(child);
        return [child];
      }

      const value = child.value.replace(
        /\$\\?(rightarrow|leftarrow|leftrightarrow|Rightarrow|Leftarrow|Leftrightarrow)\$/g,
        (_match, command: string) => ARROWS[command]
      );
      const parts: MarkdownNode[] = [];
      const bold = /\*\*([^\s*](?:[^*\n]*[^\s*])?)\*\*/g;
      let offset = 0;
      for (const match of value.matchAll(bold)) {
        parts.push({ type: "text", value: value.slice(offset, match.index) });
        parts.push({ type: "strong", children: [{ type: "text", value: match[1] }] });
        offset = match.index + match[0].length;
      }
      parts.push({ type: "text", value: value.slice(offset) });
      return parts;
    });
  };
}
