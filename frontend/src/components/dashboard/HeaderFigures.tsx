import { Money } from "../shared/Money";

interface HeaderFiguresProps {
  totalOut: string;
  totalIn: string;
  net: string;
}

export function HeaderFigures({ totalOut, totalIn, net }: HeaderFiguresProps) {
  return (
    <div className="mb-10 flex flex-wrap items-end justify-between gap-8 border-b border-hairline pb-8">
      <div>
        <p className="mb-1 text-sm text-ink-secondary">Total out</p>
        <p className="text-[56px] leading-none font-medium tracking-tight text-accent tabular-nums">
          <Money value={totalOut} absolute />
        </p>
      </div>
      <div className="flex gap-10">
        <div>
          <p className="mb-1 text-sm text-ink-secondary">Total in</p>
          <p className="text-2xl tracking-tight text-ink tabular-nums">
            <Money value={totalIn} absolute />
          </p>
        </div>
        <div>
          <p className="mb-1 text-sm text-ink-secondary">Net</p>
          <p className="text-2xl tracking-tight tabular-nums">
            <Money value={net} />
          </p>
        </div>
      </div>
    </div>
  );
}
