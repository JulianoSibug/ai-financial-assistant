import type { HealthResponse } from "../../lib/types";
import { Button } from "../shared/Button";
import { EmptyState } from "../shared/EmptyState";

interface SetupViewProps {
  health: HealthResponse;
  onReadStatements: () => void;
  starting: boolean;
}

export function SetupView({ health, onReadStatements, starting }: SetupViewProps) {
  if (!health.dir_exists) {
    return (
      <EmptyState
        title="Statements folder not found"
        detail={`Ledger looked for statements at ${health.statements_dir} and that path doesn't exist. Create the folder, add your PDF or CSV statements, and set STATEMENTS_DIR in .env if it should point somewhere else.`}
      />
    );
  }

  if (health.file_count === 0) {
    return (
      <EmptyState
        title="No statement files found"
        detail={`Ledger looked at ${health.statements_dir} and found no PDF, CSV, OFX, or QFX files. Add your statements there and reload.`}
      />
    );
  }

  return (
    <EmptyState
      title={`${health.file_count} file${health.file_count === 1 ? "" : "s"} found at ${health.statements_dir}`}
      detail="Ledger hasn't read these yet. Nothing leaves your machine except category labels and merchant names sent to the LLM for classification."
      action={
        <Button variant="primary" onClick={onReadStatements} disabled={starting}>
          {starting ? "Starting…" : "Read statements"}
        </Button>
      }
    />
  );
}
