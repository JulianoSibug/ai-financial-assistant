import { useCallback, useEffect, useState } from "react";
import { PageShell } from "./components/layout/PageShell";
import { TopBar } from "./components/layout/TopBar";
import { ProcessingView } from "./components/processing/ProcessingView";
import { SetupView } from "./components/setup/SetupView";
import { DashboardView } from "./components/dashboard/DashboardView";
import { TransactionsView } from "./components/transactions/TransactionsView";
import { ApiError, getHealth, getSummary, startAnalyze, startIngest } from "./lib/api";
import type { HealthResponse, SummaryPayload } from "./lib/types";

type Stage =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "setup"; health: HealthResponse }
  | { kind: "processing-ingest"; url: string }
  | { kind: "processing-analyze"; url: string }
  | { kind: "ready"; health: HealthResponse; summary: SummaryPayload };

export default function App() {
  const [stage, setStage] = useState<Stage>({ kind: "loading" });
  const [view, setView] = useState<"dashboard" | "transactions">("dashboard");
  const [starting, setStarting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const loadInitial = useCallback(async () => {
    try {
      const health = await getHealth();
      try {
        const summary = await getSummary();
        setStage({ kind: "ready", health, summary });
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          setStage({ kind: "setup", health });
        } else {
          throw e;
        }
      }
    } catch (e) {
      setStage({ kind: "error", message: e instanceof Error ? e.message : "Failed to reach the Ledger backend." });
    }
  }, []);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  async function handleReadStatements() {
    setStarting(true);
    try {
      const { job_id } = await startIngest();
      setStage({ kind: "processing-ingest", url: `/api/ingest/status?job_id=${job_id}` });
    } catch (e) {
      setStage({ kind: "error", message: e instanceof Error ? e.message : "Failed to start ingest." });
    } finally {
      setStarting(false);
    }
  }

  async function handleGenerateSummary() {
    setGenerating(true);
    try {
      const { job_id } = await startAnalyze();
      setStage({ kind: "processing-analyze", url: `/api/analyze/status?job_id=${job_id}` });
    } catch (e) {
      setStage({ kind: "error", message: e instanceof Error ? e.message : "Failed to start analysis." });
    } finally {
      setGenerating(false);
    }
  }

  if (stage.kind === "loading") {
    return (
      <PageShell>
        <p className="text-sm text-ink-secondary">Loading…</p>
      </PageShell>
    );
  }

  if (stage.kind === "error") {
    return (
      <PageShell>
        <TopBar view={view} onViewChange={setView} showNav={false} />
        <p className="text-sm text-accent">{stage.message}</p>
      </PageShell>
    );
  }

  if (stage.kind === "setup") {
    return (
      <PageShell>
        <TopBar view={view} onViewChange={setView} showNav={false} />
        <SetupView health={stage.health} onReadStatements={handleReadStatements} starting={starting} />
      </PageShell>
    );
  }

  if (stage.kind === "processing-ingest") {
    return (
      <PageShell>
        <TopBar view={view} onViewChange={setView} showNav={false} />
        <ProcessingView url={stage.url} title="Reading statements" onDone={loadInitial} />
      </PageShell>
    );
  }

  if (stage.kind === "processing-analyze") {
    return (
      <PageShell>
        <TopBar view={view} onViewChange={setView} showNav={false} />
        <ProcessingView url={stage.url} title="Analyzing" onDone={loadInitial} />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <TopBar period={stage.summary.period} view={view} onViewChange={setView} showNav />
      {view === "dashboard" ? (
        <DashboardView summary={stage.summary} onGenerateSummary={handleGenerateSummary} generating={generating} />
      ) : (
        <TransactionsView />
      )}
    </PageShell>
  );
}
