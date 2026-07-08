# pharma-epi — epidemiology ingestion suite + quarterly monitor

Deployable bundle of the epidemiology-ingestion skills **and** the state the
scheduled monitor needs. Two ways it's used:

1. **Locally** — copy `skills/*` into `~/.claude/skills/` and run them by hand
   (the on-demand path). See each skill's `SKILL.md`.
2. **As a scheduled cloud routine** — a headless run clones THIS repo, runs the
   fetcher to pull any new epi reports, and **commits the updated ledger back**
   so the next run remembers what's already been grabbed. See
   `skills/pharma-epi-fetcher/reference/routine-setup.md`.

## Layout

```
skills/
  pharma-epi-fetcher/     ← quarterly watchlist puller (NEW): discovery + fetch + dedup
    watchlist.yaml          the sources to monitor (edit this to add companies)
    ledger.json             DEDUP STATE — what's been grabbed (tracked; the repo's memory)
    fetch.py                deterministic download/dedup/manifest core (stdlib only)
    coverage.py             renders coverage.md (held vs. gaps, per company/project)
  pharma-epi-extractor/   ← reads a source doc → staging CSVs + review note
  pharma-epi-exporter/    ← writes staged rows into the master (export.py)
  pharma-epi-qc/          ← read-only standardization audit (qc.py)
  pharma-epi-pipeline/    ← orchestrates extractor → checkpoint → exporter → qc
```

The fetcher sits **upstream**: `fetcher → extractor → [human checkpoint] → exporter → qc`.

## Why the ledger is committed

`ledger.json` is the monitor's memory. A cloud run happens on a fresh, throwaway
sandbox with no local state, so it **reads the ledger from this repo at start and
commits it back at end** — otherwise every run would think every report is new.
Downloaded report binaries are NOT tracked (`.gitignore`); they go to Box / a
local inbox. The repo holds code + state + audit trail only.

## Monitoring cadence

The four seeded sources publish on different clocks (GSK quarterly, Roche annual
~September, Novartis annual, Sanofi sporadic events), so the monitor runs
**monthly** — cheap idempotent re-scans that never miss a window by more than a
few weeks. See `routine-setup.md` for the cron and setup prerequisites.

## Compliance (RAC)

Contains internal references (the Epidemiology Master Sheet Box id, workflow) and
is intended for an **RAC-approved private** location only. Everything the suite
produces is AI-assisted research: independently verify before use, never the sole
basis for a decision, retain per RAC recordkeeping. No secrets in the repo — the
Box API token is supplied only via an environment variable / managed secret.
