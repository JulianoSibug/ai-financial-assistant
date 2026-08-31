// Every money value arrives from the backend as a decimal string. Parsing
// to Number here is strictly for *display* -- never feed the result back
// into a calculation; the backend already did the math.

const moneyFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatMoney(value: string): string {
  const n = Number(value);
  const abs = moneyFormatter.format(Math.abs(n));
  return n < 0 ? `-${abs}` : abs;
}

export function formatMoneyAbs(value: string): string {
  return moneyFormatter.format(Math.abs(Number(value)));
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

export function formatDate(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export function formatDateLong(iso: string): string {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });
}

export function formatPeriodLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
  });
}

export function isNegative(value: string): boolean {
  return value.trim().startsWith("-");
}
