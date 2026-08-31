import { useEffect } from "react";
import { useJobStream } from "../../lib/useJobStream";
import { Banner } from "../shared/Banner";
import { ProgressLog } from "./ProgressLog";

interface ProcessingViewProps {
  url: string;
  title: string;
  onDone: () => void;
}

export function ProcessingView({ url, title, onDone }: ProcessingViewProps) {
  const { events, latest, done, error } = useJobStream(url);

  useEffect(() => {
    if (done) {
      const timer = setTimeout(onDone, 500);
      return () => clearTimeout(timer);
    }
  }, [done, onDone]);

  return (
    <div className="animate-fade-in">
      <h2 className="mb-1 text-xl text-ink">{title}</h2>
      <p className="mb-6 text-sm text-ink-secondary">
        {error ? "Something went wrong." : done ? "Done." : (latest?.message ?? "Starting…")}
      </p>
      {error && (
        <div className="mb-6">
          <Banner tone="warning" dismissible={false}>
            {error}
          </Banner>
        </div>
      )}
      <ProgressLog events={events.filter((e) => e.type !== "error")} />
    </div>
  );
}
