import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";

export default function TableContent({ text }: { text: string }) {
  return (
    <ReactMarkdown remarkPlugins={[[remarkGfm, { singleTilde: false }]]} rehypePlugins={[rehypeRaw, rehypeSanitize]}>
      {text}
    </ReactMarkdown>
  );
}
