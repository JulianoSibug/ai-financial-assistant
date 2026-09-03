import { useCallback, useEffect, useState } from "react";
import { PageShell } from "./components/layout/PageShell";
import { TopBar } from "./components/layout/TopBar";
import { ProcessingView } from "./components/processing/ProcessingView";
import { SetupView } from "./components/setup/SetupView";
import { DashboardView } from "./components/dashboard/DashboardView";
import { TransactionsView } from "./components/transactions/TransactionsView";
import { ApiError, getFixRequests, getHealth, getPeriods, getSummary, resolveFixRequest, startAnalyze, startIngest } from "./lib/api";
import type { FixRequest, HealthResponse, Period, SummaryPayload } from "./lib/types";

type Stage =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "setup"; health: HealthResponse }
  | { kind: "processing-ingest"; url: string; returnToPeriod?: string }
  | { kind: "processing-analyze"; url: string; period: string }
  | { kind: "ready"; health: HealthResponse; summary: SummaryPayload; periods: Period[]; fixRequests: FixRequest[] };

export default function App() {
  const [stage, setStage] = useState<Stage>({ kind: "loading" });
  const [view, setView] = useState<"dashboard" | "transactions">("dashboard");
  const [starting, setStarting] = useState(false);
  const [generating, setGenerating] = useState(false);

  const loadInitial = useCallback(async (period?: string) => {
    try {
      const health = await getHealth();
      try {
        const summary = await getSummary(period);
        const periods = await getPeriods();
        const fixRequests = await getFixRequests();
        setStage({ kind: "ready", health, summary, periods, fixRequests });
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
    const returnToPeriod = stage.kind === "ready" ? stage.summary.period : undefined;
    setStarting(true);
    try {
      const { job_id } = await startIngest();
      setStage({ kind: "processing-ingest", url: `/api/ingest/status?job_id=${job_id}`, returnToPeriod });
    } catch (e) {
      setStage({ kind: "error", message: e instanceof Error ? e.message : "Failed to start ingest." });
    } finally {
      setStarting(false);
    }
  }

  async function handleResolveFixRequest(id: number, status: "resolved" | "dismissed") {
    if (stage.kind !== "ready") return;
    const previous = stage.fixRequests;
    setStage({ ...stage, fixRequests: previous.filter((r) => r.id !== id) });
    try {
      await resolveFixRequest(id, status);
    } catch {
      setStage((s) => (s.kind === "ready" ? { ...s, fixRequests: previous } : s));
    }
  }

  async function handlePeriodChange(period: string) {
    if (stage.kind !== "ready") return;
    try {
      const summary = await getSummary(period);
      setStage({ ...stage, summary });
    } catch (e) {
      setStage({ kind: "error", message: e instanceof Error ? e.message : "Failed to load that period." });
    }
  }

  async function handleGenerateSummary() {
    if (stage.kind !== "ready") return;
    const period = stage.summary.period;
    setGenerating(true);
    try {
      const { job_id } = await startAnalyze(period);
      setStage({ kind: "processing-analyze", url: `/api/analyze/status?job_id=${job_id}`, period });
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
        <ProcessingView url={stage.url} title="Reading statements" onDone={() => loadInitial(stage.returnToPeriod)} />
      </PageShell>
    );
  }

  if (stage.kind === "processing-analyze") {
    return (
      <PageShell>
        <TopBar view={view} onViewChange={setView} showNav={false} />
        <ProcessingView url={stage.url} title="Analyzing" onDone={() => loadInitial(stage.period)} />
      </PageShell>
    );
  }

  return (
    <PageShell>
      <TopBar
        period={stage.summary.period}
        periods={stage.periods}
        onPeriodChange={handlePeriodChange}
        view={view}
        onViewChange={setView}
        showNav
        onCheckForUpdates={handleReadStatements}
        checking={starting}
      />
      {view === "dashboard" ? (
        <DashboardView
          summary={stage.summary}
          onGenerateSummary={handleGenerateSummary}
          generating={generating}
          fixRequests={stage.fixRequests}
          onResolveFixRequest={handleResolveFixRequest}
        />
      ) : (
        <TransactionsView />
      )}
    </PageShell>
  );
}
