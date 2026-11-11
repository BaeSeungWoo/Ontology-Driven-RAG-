import ReactMarkdown from "react-markdown";
import type { Element, Root, Text } from "hast";
import styles from "./figureExplanation.module.css";

// Markdown을 먼저 해석해 강조·인라인 코드의 주소도 찾고 기존 링크는 보존한다.
export function signalButtons(addresses: ReadonlySet<string>) {
  return () => (root: Root) => {
    function visit(parent: Root | Element) {
      parent.children = parent.children.flatMap((node): typeof parent.children => {
        if (node.type === "element" && node.tagName !== "a") visit(node);
        if (node.type !== "text") return [node];
        const parts: (Text | Element)[] = [];
        let end = 0;
        for (const match of node.value.matchAll(/(?<![\w.])[GFYXRAKTCD]\d{1,5}\.[0-7](?!\w|\.\d)/gi)) {
          const address = match[0].toUpperCase();
          if (!addresses.has(address)) continue;
          parts.push({ type: "text", value: node.value.slice(end, match.index) },
            { type: "element", tagName: "button", properties: { value: address }, children: [{ type: "text", value: match[0] }] });
          end = match.index + match[0].length;
        }
        return end ? [...parts, { type: "text", value: node.value.slice(end) }] : [node];
      });
    }
    visit(root);
  };
}

export function SignalButton({ address, children, onSelect }: {
  address: string; children: React.ReactNode; onSelect: (address: string) => void;
}) {
  return <button type="button" className={styles.signalLink} title={`${address} 사용처 보기`}
    onClick={() => onSelect(address)}>{children}</button>;
}

export default function LadderAnswer({ text, addresses, onSelect }: {
  text: string; addresses: ReadonlySet<string>; onSelect: (address: string) => void;
}) {
  return <ReactMarkdown rehypePlugins={[signalButtons(addresses)]} components={{
    button: ({ value, children }) => <SignalButton address={String(value)} onSelect={onSelect}>{children}</SignalButton>,
  }}>{text}</ReactMarkdown>;
}
