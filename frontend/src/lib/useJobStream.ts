import { useEffect, useRef, useState } from "react";
import type { JobEvent } from "./types";

interface JobStreamState {
  events: JobEvent[];
  latest: JobEvent | null;
  done: boolean;
  error: string | null;
}

const EMPTY_STATE: JobStreamState = { events: [], latest: null, done: false, error: null };

/** Subscribes to one of the SSE progress endpoints (/api/ingest/status or
 * /api/analyze/status). Pass null to stay disconnected. */
export function useJobStream(url: string | null): JobStreamState {
  const [state, setState] = useState<JobStreamState>(EMPTY_STATE);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!url) {
      setState(EMPTY_STATE);
      return;
    }
    setState(EMPTY_STATE);

    const source = new EventSource(url);
    sourceRef.current = source;

    source.onmessage = (e) => {
      let event: JobEvent;
      try {
        event = JSON.parse(e.data);
      } catch {
        return;
      }
      setState((prev) => ({
        events: [...prev.events, event],
        latest: event,
        done: event.type === "done",
        error: event.type === "error" ? (event.message ?? "Unknown error") : prev.error,
      }));
      if (event.type === "done" || event.type === "error") {
        source.close();
      }
    };

    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        setState((prev) => (prev.done || prev.error ? prev : { ...prev, error: "Connection to server lost." }));
      }
    };

    return () => {
      source.close();
    };
  }, [url]);

  return state;
}
