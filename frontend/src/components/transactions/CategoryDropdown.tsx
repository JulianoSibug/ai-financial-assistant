import { CATEGORIES } from "../../lib/categories";

interface CategoryDropdownProps {
  value: string | null;
  onChange: (category: string) => void;
}

export function CategoryDropdown({ value, onChange }: CategoryDropdownProps) {
  return (
    <select
      value={value ?? "Uncategorized"}
      onChange={(e) => onChange(e.target.value)}
      className="border border-transparent bg-transparent py-1 text-sm text-ink hover:border-hairline focus:border-ink"
    >
      {CATEGORIES.map((c) => (
        <option key={c} value={c}>
          {c}
        </option>
      ))}
    </select>
  );
}
