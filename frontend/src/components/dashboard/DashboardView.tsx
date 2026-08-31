import type { SummaryPayload } from "../../lib/types";
import { Button } from "../shared/Button";
import { CategoryBreakdown } from "./CategoryBreakdown";
import { DailySpendChart } from "./DailySpendChart";
import { HeaderFigures } from "./HeaderFigures";
import { NarrativeReport } from "./NarrativeReport";
import { ReconciliationBanner } from "./ReconciliationBanner";
import { RecurringCharges } from "./RecurringCharges";
import { TopMerchants } from "./TopMerchants";

interface DashboardViewProps {
  summary: SummaryPayload;
  onGenerateSummary: () => void;
  generating: boolean;
}

export function DashboardView({ summary, onGenerateSummary, generating }: DashboardViewProps) {
  return (
    <div className="animate-fade-in">
      <HeaderFigures totalOut={summary.total_out} totalIn={summary.total_in} net={summary.net} />

      <ReconciliationBanner warnings={summary.reconciliation_warnings} />

      <section className="mb-10">
        <div className="mb-4 flex items-baseline justify-between">
          <h2 className="text-sm text-ink-secondary">Summary</h2>
          <Button onClick={onGenerateSummary} disabled={generating}>
            {generating ? "Generating…" : summary.narrative_markdown ? "Regenerate summary" : "Generate summary"}
          </Button>
        </div>
        <NarrativeReport markdown={summary.narrative_markdown} />
      </section>

      <div className="grid grid-cols-1 gap-10 md:grid-cols-2">
        <section>
          <h2 className="mb-4 text-sm text-ink-secondary">Category breakdown</h2>
          <CategoryBreakdown categories={summary.category_totals} />
        </section>

        <section>
          <h2 className="mb-4 text-sm text-ink-secondary">Daily spend</h2>
          <DailySpendChart data={summary.daily_series} />
        </section>

        <section>
          <h2 className="mb-4 text-sm text-ink-secondary">Top merchants</h2>
          <TopMerchants merchants={summary.top_merchants} />
        </section>

        <section>
          <h2 className="mb-4 text-sm text-ink-secondary">Recurring charges</h2>
          <RecurringCharges charges={summary.recurring_charges} />
        </section>
      </div>
    </div>
  );
}
