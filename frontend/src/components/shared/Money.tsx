import { formatMoney, formatMoneyAbs, isNegative } from "../../lib/format";

interface MoneyProps {
  value: string;
  className?: string;
  /** Show absolute value without a leading minus sign (headline figures
   * that already communicate direction via a label, e.g. "Total out"). */
  absolute?: boolean;
}

export function Money({ value, className = "", absolute = false }: MoneyProps) {
  const negative = isNegative(value);
  const text = absolute ? formatMoneyAbs(value) : formatMoney(value);
  return <span className={`tabular-nums ${negative ? "text-accent" : "text-ink"} ${className}`}>{text}</span>;
}
