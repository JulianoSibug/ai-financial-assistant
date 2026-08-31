import type { ReactNode } from "react";

export function PageShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-paper">
      <div className="mx-auto max-w-[1100px] px-6 py-10 sm:px-10">{children}</div>
    </div>
  );
}
