export function ExtractionBadge({ method }: { method: string }) {
  if (method !== "llm") return null;
  return (
    <span
      title="Extracted by the LLM fallback -- worth a spot-check"
      className="ml-2 border border-hairline px-1.5 py-0.5 text-[10px] text-ink-secondary"
    >
      LLM
    </span>
  );
}
