import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function NarrativeReport({ markdown }: { markdown: string | null }) {
  if (!markdown) {
    return <p className="text-sm text-ink-secondary">No summary yet. Generate one from the dashboard header.</p>;
  }

  return (
    <div className="max-w-[70ch] text-[15px] leading-relaxed text-ink">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h3: (props) => <h3 className="mb-3 text-lg font-medium text-ink" {...props} />,
          p: (props) => <p className="mb-4" {...props} />,
          ul: (props) => <ul className="mb-4 list-disc space-y-1.5 pl-5" {...props} />,
          ol: (props) => <ol className="mb-4 list-decimal space-y-1.5 pl-5" {...props} />,
          li: (props) => <li {...props} />,
          strong: (props) => <strong className="font-semibold text-ink" {...props} />,
          table: (props) => <table className="mb-4 w-full text-sm" {...props} />,
          th: (props) => <th className="border-b border-hairline pb-1 text-left font-normal text-ink-secondary" {...props} />,
          td: (props) => <td className="border-b border-hairline py-1" {...props} />,
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}
