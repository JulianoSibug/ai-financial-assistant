import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import type { PeriodTotal } from "../../lib/types";
import { formatPeriodLabel, formatMoneyAbs } from "../../lib/format";

interface TooltipPayloadItem {
  payload: PeriodTotal;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayloadItem[] }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div className="border border-hairline bg-paper px-3 py-2 text-sm">
      <p className="text-ink-secondary">{formatPeriodLabel(point.period)}</p>
      <p className="tabular-nums text-ink">{formatMoneyAbs(point.total_out)}</p>
    </div>
  );
}

export function TrendsChart({ data }: { data: PeriodTotal[] }) {
  if (data.length < 2) return null;

  const chartData = data.map((d) => ({ ...d, value: Number(d.total_out) }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="period"
            tickFormatter={formatPeriodLabel}
            axisLine={{ stroke: "#E3E1DD" }}
            tickLine={false}
            interval="preserveStartEnd"
            tick={{ fontSize: 11, fill: "#5C5C5C" }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "#E3E1DD", opacity: 0.5 }} />
          <Bar dataKey="value" fill="#1B3A6B" radius={[2, 2, 0, 0]} maxBarSize={40} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
