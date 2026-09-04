import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import type { DailyPoint } from "../../lib/types";
import { formatDate, formatMoneyAbs } from "../../lib/format";

interface TooltipPayloadItem {
  payload: DailyPoint;
}

function ChartTooltip({ active, payload }: { active?: boolean; payload?: TooltipPayloadItem[] }) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div className="border border-hairline bg-paper px-3 py-2 text-sm">
      <p className="text-ink-secondary">{formatDate(point.date)}</p>
      <p className="tabular-nums text-ink">{formatMoneyAbs(point.total_out)}</p>
    </div>
  );
}

interface DailySpendChartProps {
  data: DailyPoint[];
  selectedDate?: string | null;
  onSelectDay?: (date: string) => void;
}

export function DailySpendChart({ data, selectedDate, onSelectDay }: DailySpendChartProps) {
  const chartData = data.map((d) => ({ ...d, value: Number(d.total_out) }));

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            axisLine={{ stroke: "#E3E1DD" }}
            tickLine={false}
            interval="preserveStartEnd"
            tick={{ fontSize: 11, fill: "#5C5C5C" }}
          />
          <Tooltip content={<ChartTooltip />} cursor={{ fill: "#E3E1DD", opacity: 0.5 }} />
          <Bar dataKey="value" radius={[2, 2, 0, 0]} maxBarSize={18} isAnimationActive={false}>
            {chartData.map((d) => (
              <Cell
                key={d.date}
                fill="#1B3A6B"
                fillOpacity={selectedDate ? (d.date === selectedDate ? 1 : 0.3) : 1}
                onClick={onSelectDay ? () => onSelectDay(d.date) : undefined}
                style={onSelectDay ? { cursor: "pointer" } : undefined}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
