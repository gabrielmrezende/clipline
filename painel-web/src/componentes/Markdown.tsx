import ReactMarkdown from "react-markdown";

export function Markdown({ texto }: { texto: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown>{texto}</ReactMarkdown>
    </div>
  );
}
