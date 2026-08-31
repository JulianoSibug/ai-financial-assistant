import type { JobEvent } from "../../lib/types";

export function ProgressLog({ events }: { events: JobEvent[] }) {
  const withMessages = events.filter((e) => e.message);

  if (withMessages.length === 0) {
    return null;
  }

  return (
    <div className="border border-hairline">
      <div className="max-h-80 divide-y divide-hairline overflow-y-auto">
        {withMessages.map((e, i) => (
          <div key={i} className="flex justify-between gap-4 px-4 py-2 text-sm text-ink-secondary">
            <span className="truncate">{e.message}</span>
            {e.current != null && e.total != null && e.total > 0 && (
              <span className="shrink-0 tabular-nums">
                {e.current}/{e.total}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
