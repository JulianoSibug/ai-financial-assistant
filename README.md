# Ledger

An AI Financial Assistant. It reads your bank and credit-card statements
off disk, categorizes the transactions, reconciles them against what each
statement actually claims, and writes a plain-language summary of where
your money went. Everything today runs on your machine: no cloud database,
no accounts, no hosting. The only thing that ever leaves your machine is a
redacted slice of transaction data sent to an LLM for categorization,
narrative, and (as chat lands) conversational answers -- never a dollar
figure it computed itself.

## What Ledger does

Ledger is built around seven standing capabilities. Some are fully built,
some are in progress this phase, some are intentionally deferred -- noted
honestly below rather than promised ahead of time.

1. **Categorize transactions** -- built. Fixed taxonomy, LLM-assigned,
   cached per merchant so a second run over the same data makes almost no
   LLM calls.
2. **Find patterns in summaries and transactions** -- in progress. A
   deterministic recurring-charge detector was tried and removed: the
   same-amount/consecutive-months heuristic produced too many false
   positives to trust. Waits on chat tool-calling instead.
3. **Generate summary reports on request** -- built as a one-shot monthly
   narrative; on-demand/multi-period generation via chat is in progress.
4. **Handle interactions through a chat interface** -- in progress.
5. **Save context of previous chat logs** -- in progress, alongside chat
   (persisted, resumable conversation history).
6. **Give advice/observations based on user questions** -- in progress, via
   chat tool-calling: the LLM only ever selects and phrases numbers a
   backend tool already computed from real data -- it never sums anything
   itself. Same guarantee the narrative summary already has, extended to
   a conversational surface.
7. **Create parsing code** -- planned, and deliberately supervised, not
   unattended: an agent proposes parsing fixes (with a required regression
   test, validated against every previously-seen statement) that a person
   reviews and approves before anything applies. The parsing code in this
   repo today was written by hand, one real statement format at a time --
   this capability is about making that process repeatable and safe rather
   than replacing the judgment involved in it.

## Roadmap

Ledger is being built in five phases:

1. **Working locally** (current) -- everything above, entirely on your
   machine.
2. **Plaid integration** -- live bank connections that supplement, not
   replace, statement file parsing.
3. **Cloud deployed** -- auth, multi-tenant storage, and the security work
   that comes with hosting other people's financial data.
4. **Internal test group** -- private invitations for feedback and
   iteration.
5. **Ship and sell** -- a real product, if it gets there.

Detailed phase-by-phase design notes live in a local, untracked
`PHASE_PLAN.md` -- internal roadmap thinking, not documentation for anyone
else who clones this repo, which is why it isn't committed.

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
| `LLM_PROVIDER` | `claude_cli` (default), `anthropic_api`, or `manual` (temporary categorization-only stand-in -- see "How the LLM is used" below). |
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
   breakdowns, top merchants) and asked to write prose around it. It's
   explicitly instructed not to calculate or estimate anything.

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
- **`manual`** is a temporary stand-in for environments where `claude` isn't
  reachable at all (this has been true throughout this project's own
  development sandbox). `backend/llm/manual_provider.py` implements the
  same provider interface as the two real ones, but instead of calling a
  model it looks each transaction's merchant up in a hand-assigned mapping
  (`MERCHANT_CATEGORIES`) covering the real statements this app has been
  tested against. A merchant not in that mapping falls back to
  Uncategorized at low confidence, same as a real model would for a
  genuinely ambiguous one. It **only** covers categorization -- the
  narrative summary still needs a real model, since fresh prose for
  whatever stats happen to be computed isn't something a fixed lookup can
  produce; asking for one returns a plain-language message saying so
  instead of fabricating text or crashing. Switch back to `claude_cli` or
  `anthropic_api` once a real connection is available -- nothing else in
  the app needs to change either way, since `categorize_all()` doesn't know
  or care which provider it's talking to.

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
