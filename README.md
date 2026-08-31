# Ledger

A local-only spend summary app. It reads your bank and credit-card statements
off disk, categorizes the transactions, and writes a plain-language summary
of where your money went. Everything runs on your machine: no cloud
database, no accounts, no hosting. The only thing that ever leaves your
machine is a redacted slice of transaction data sent to an LLM for
categorization and prose -- never a dollar figure it computed itself.

## Prerequisites

- Python 3.11+ (3.14 confirmed working)
- Node 18+
- The [Claude Code CLI](https://claude.com/claude-code) installed and logged
  in (`claude` on your `PATH`) -- needed for the default LLM path. Skip this
  if you plan to use the Anthropic API provider instead (see below).
- `uv` is used automatically if installed; otherwise `run.sh` falls back to
  a standard `venv` + `pip`.

## First run

1. Point Ledger at your statements. Copy `.env.example` to `.env` and set
   `STATEMENTS_DIR` to the folder containing your PDF/CSV statements:

   ```bash
   cp .env.example .env
   ```

   ```ini
   STATEMENTS_DIR="~/Documents/Financial Statements/Aug 2026"
   ```

2. If you're using the default LLM provider, make sure the CLI is logged in:

   ```bash
   claude  # run once interactively to complete login, then exit
   ```

3. Start it:

   ```bash
   ./run.sh
   ```

   This installs backend and frontend dependencies on first run, starts the
   API and the dev server, and prints one URL
   (`http://localhost:5173`). Open it, and you'll land on a setup screen
   showing the folder Ledger is looking at and how many files it found.
   Click **Read statements**, then **Generate summary**.

   There's also a **`Ledger.command`** shortcut on the Desktop -- double-click
   it instead of using the terminal. It starts both servers, opens your
   browser automatically once they're ready, and cleans both up when you
   close its window or press Ctrl-C. It hardcodes this project's path, so if
   you ever move the folder, regenerate it or edit the `PROJECT_DIR` line at
   the top.

4. For a one-process build (no separate dev server):

   ```bash
   cd frontend && npm run build && cd ..
   ./run.sh --prod
   ```

   This serves the built frontend and the API from a single port
   (`http://127.0.0.1:8000` by default).

Re-running ingest is safe and cheap: files already seen (by content hash)
are skipped, and re-running analysis over the same data makes almost no LLM
calls, because categorization results are cached per merchant.

## Configuration (`.env`)

| Variable | Meaning |
|---|---|
| `STATEMENTS_DIR` | Folder to scan for statements. Quote it if the path has spaces. |
| `LLM_PROVIDER` | `claude_cli` (default) or `anthropic_api`. |
| `ANTHROPIC_API_KEY` | Only needed for `anthropic_api`. |
| `ANTHROPIC_MODEL` | Optional. Overrides the model for *both* categorization and the narrative. Leave unset to use the built-in per-task defaults (a small/fast model for categorization, a stronger one for the narrative). |
| `DB_PATH` | Where the local SQLite database lives (created automatically). |
| `HOST` / `PORT` | Backend bind address. Always `127.0.0.1` by default -- there's no auth, so it should never be exposed beyond your own machine. |

## How the LLM is used

**The LLM never computes a number.** Every total, percentage, and chart you
see is computed in Python from parsed transaction data. The LLM does exactly
two things:

1. **Categorization** (`backend/llm/categorize.py`) -- given a batch of
   `{id, merchant, amount, date}`, it assigns one category from a fixed
   taxonomy and a transfer flag. Never the raw description, never account
   info. Results are cached in SQLite keyed by normalized merchant name, so
   "STARBUCKS #4471" and "STARBUCKS #0092" are classified once and reused
   forever -- a second run over the same month makes close to zero LLM calls.
2. **The narrative summary** (`backend/llm/summarize.py`) -- handed a
   finished block of already-computed statistics (totals, category
   breakdowns, top merchants, recurring charges) and asked to write prose
   around it. It's explicitly instructed not to calculate or estimate
   anything.

**Redaction happens first, always** (`backend/llm/redact.py`). Before any
text reaches the model -- including the PDF-extraction fallback below --
account numbers, card numbers, SSNs, and street addresses are stripped.
Merchant names and dollar amounts pass through, since the model needs those
to do its job.

There's also a narrower **PDF extraction fallback**
(`backend/ingest/parse_pdf.py`): most statements are read by a
deterministic regex parser, but if a page's transactions don't match that
shape, a redacted copy of that page's text is sent to the model asking for a
JSON array of transactions back. Rows recovered this way are tagged
`extraction_method: "llm"` in the transactions table so you can spot-check
them.

**Provider choice:**

- **`claude_cli` (default)** shells out to the Claude Code CLI in headless
  mode (`claude -p --output-format json ...`). This draws on your **Claude
  Pro subscription's usage limits**, shared with your normal interactive
  Claude Code usage -- it is not billed per-token. A large first-time ingest
  across many months (before the cache has anything in it) can use a
  meaningful chunk of that quota in one sitting; a second run over the same
  data will not.
- **`anthropic_api`** posts directly to the Anthropic Messages API with an
  `ANTHROPIC_API_KEY`, billed per token. Switch to this if you ever host or
  share this app -- the CLI path assumes a personal, already-authenticated
  session on the same machine, which doesn't make sense for a shared
  deployment. Set `LLM_PROVIDER=anthropic_api` and `ANTHROPIC_API_KEY` in
  `.env`; nothing else in the app changes.

## Troubleshooting

**A PDF's transactions don't show up, or show up with an "LLM" badge you
didn't expect.** The regex parser expects lines shaped like
`DATE  DESCRIPTION  AMOUNT` with a `MM/DD/YYYY`-style date. Statement
layouts vary a lot -- multi-column tables, running balances printed as a
third field, or dates without a year will all reduce what the regex parser
recovers, triggering the LLM fallback (or, if the LLM isn't available
either, that page will contribute no transactions). If a whole page is
missing, check `backend/ingest/parse_pdf.py`'s `_PDF_LINE_RE` against a
copy of the actual extracted text (pdfplumber's `extract_text()` output) --
it's a deliberately simple pattern meant to be extended once you know what
your bank's actual layout looks like, not an exhaustive one.

**`claude` not on PATH / "LLM provider 'claude_cli' is not ready".** This
usually means the standalone Claude Code CLI isn't installed, even if
you use Claude Code through an editor extension -- those are separate
installs. Install it, confirm `which claude` resolves, and run `claude`
once interactively to finish login. `GET /api/health` reports
`llm_authenticated` and `llm_auth_detail` if you want to check this without
starting a full analysis.

## Tests

```bash
./.venv/bin/python -m pytest backend/tests/
```

Covers redaction, amount sign normalization (including parenthesized
negatives and debit/credit column layouts), merchant normalization,
deduplication across overlapping statement files, a reconciliation fixture
engineered to fail, and categorization response validation (malformed JSON,
unknown categories, omitted transactions). Two synthetic fixtures (one CSV,
one PDF built with `reportlab`) are generated at test time rather than
committed, since `*.pdf`/`*.csv` are gitignored.

## Project layout

```
backend/
  main.py, config.py, models.py, db.py, jobs.py
  ingest/   discover, parse_csv, parse_pdf, normalize, reconcile
  llm/      provider, claude_cli, anthropic_api, categorize, summarize, redact
  tests/
frontend/
  src/  App.tsx, components/{layout,setup,processing,dashboard,transactions,shared}, lib/
```
