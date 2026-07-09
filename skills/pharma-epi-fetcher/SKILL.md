---
name: pharma-epi-fetcher
description: >-
  Upstream skill that automatically pulls epidemiology (patient-population)
  source documents from a user-maintained watchlist of pharma companies, dedupes
  them against an ingestion ledger, and hands each NEW report to the
  pharma-epi-extractor — auto-extracting to (but never past) the human
  checkpoint. Use when the user says "pull the quarterly epi reports", "check the
  watchlist", "fetch new epi sources", "run the quarterly epi pull", or wants to
  find/download the latest epidemiology reports across tracked companies. Designed
  to run on-demand locally now and, later, as an unattended quarterly cloud
  routine. Does NOT write to the master sheet and NEVER crosses the sign-off gate.
version: 1
---

# pharma-epi-fetcher

The **discovery + fetch** front-end of the epi pipeline. It sits upstream of the
existing skills and feeds them one source document at a time:

```
pharma-epi-fetcher  →  pharma-epi-extractor  →  [CHECKPOINT sign-off]  →  exporter  →  qc
   (this skill)            (auto, to gate)          (human only)
```

> **Investment-use & pipeline reference:** the shared definition of done, flag
> legend, full schema, Box constraint, slug + house filename conventions, and the
> investment-use/recordkeeping rule live in
> `../pharma-epi-extractor/reference/pipeline.md`. Read it; this SKILL does not
> restate it.

## What This Skill Does

1. Reads the **watchlist** (`watchlist.yaml`) — the user's registry of epi-report sources.
2. **Discovers** the current report URL(s) per source (see the discovery ladder).
3. **Fetches + dedupes** the binaries via `fetch.py` (sha256 vs `ledger.json`), staging them locally and (in production) uploading to Box.
4. For each **new** report, invokes `pharma-epi-extractor` in **unattended mode** — producing staging CSVs + a review note with the checkpoint left **unchecked**.
5. **Hands off:** a Slack summary of what was pulled and what needs human sign-off (+ `git commit` of artifacts once the bundle lives in a repo).

## Trigger Conditions

- "pull the quarterly epi reports", "run the epi pull", "check the watchlist"
- "fetch the latest epidemiology reports for <companies>"
- "what new epi sources are out since last quarter"
- The quarterly cloud routine firing (see `reference/routine-setup.md`)

## Inputs

- `watchlist.yaml` — sources to check (user-maintained; see the file's header for the schema).
- `ledger.json` — dedup state; created empty, grows each run. Never re-fetches an already-ingested report.
- Optional: a Box app token (env var) + target folder id for the production upload path.

## Discovery ladder (how to resolve each source's report URL)

`WebFetch` returns a **text extraction, not the binary** — so it is for
*discovery only*; `fetch.py` does the actual binary download. Per watchlist entry:

- **one_off** → use `report_url` directly.
- **recurring** → resolve via, in order:
  - **A. URL pattern** — only if genuinely predictable. **Usually a trap** — pharma IR
    URLs carry opaque slugs (e.g. GSK `/media/2wgpnet2/...`). Verify every candidate;
    never extrapolate a filename across periods (Novartis 2023/2025 exist, 2021/2022/2024 404).
  - **B. Landing-page scan** — `WebFetch` the pinned `landing_url`; collect links whose
    text/href contains `link_match`; if `paginate` is set, walk pages (`?<param>=1..max_pages`)
    and collect across all of them.
  - **C. Search fallback** — `WebSearch`, then `WebFetch` to confirm the exact file.
- If nothing resolves confidently, **mark the source "needs manual pull"** — never guess or grab the wrong file.

Build a `candidates.json` (list of `{source_id, company, period, url, expected_format, adapter_hint}`)
from what you resolve, then call `fetch.py`.

## Workflow

1. Read `watchlist.yaml`.
2. For each source, resolve report URL(s) via the ladder → assemble `candidates.json`. For recurring sources, include every period not already in `ledger.json`.
3. Run the fetcher:
   ```
   python3 <skills>/pharma-epi-fetcher/fetch.py \
     --candidates <candidates.json> \
     --ledger    <skills>/pharma-epi-fetcher/ledger.json \
     --inbox     "~/Documents/Epi Source Inbox" \
     [--box-folder-id <ID> --box-token-env BOX_API_TOKEN]      # production upload; omit to stage locally
   ```
   `--dry-run` resolves + dedupes without downloading. It follows redirects and, on a
   `media.*` DNS failure, retries the `www.*` host.
4. For each **new** entry in the manifest, invoke `pharma-epi-extractor` (route via its
   `adapters/INDEX.md`) in **unattended mode** (below). Stage its CSVs + `<slug>_review.md`.
5. Regenerate the **coverage log** (below) so the held-vs-gap view stays current.
6. Hand off: post a **Slack** summary (sources checked, new count, per-report extract status,
   any "needs manual pull", what needs sign-off) and `git commit` the staging artifacts (no-op pre-repo).

## Coverage log

`coverage.py` renders a scannable "what have we grabbed" view from `ledger.json`
— per project → company, a Year×{Q1–Q4,FY} grid (✓/·) for quarterly sources,
event lists for annual/event sources, and explicit gap lines. Regenerate after
every pull:

```
python3 <skills>/pharma-epi-fetcher/coverage.py \
  --ledger <skills>/pharma-epi-fetcher/ledger.json \
  --out <working-dir>/coverage.md [--project <tag>]
```

Pulls are tagged with `--project` (default `epi-master`; a per-candidate
`project` field overrides), so coverage is grouped and filterable per project.

## Box archive & auth

When `--box-folder-id` is set, each fetched report is uploaded to that Box folder and its
`box_file_id` recorded in the ledger — git holds code + ledger, **Box holds the PDFs**. Omit
`--box-folder-id` to stage locally only. `--backfill-box` uploads already-staged files (ledger
entries lacking a `box_file_id`) without re-downloading.

Auth — env vars only, never hardcode a secret:
- **Manual runs:** `BOX_API_TOKEN` = a Box Developer Token (~60 min, from the app's console).
- **Automation (CCG):** set `BOX_CLIENT_ID`, `BOX_CLIENT_SECRET`, `BOX_ENTERPRISE_ID` and the script
  mints its own token. Optional `BOX_AS_USER_ID` makes it upload *as* that user (so files land in the
  user's folders rather than the service account's space).

Two environment facts (see `reference/routine-setup.md`):
- The Box **Custom App must be enterprise-admin-authorized**, or every call 401s
  `"Cannot authorize with this service"` (this gates even developer tokens).
- Uploads go through **curl**, not Python — RAC's Netskope TLS proxy injects a CA that Python's
  OpenSSL rejects; curl uses the system bundle (`$CURL_CA_BUNDLE`).

## Unattended mode (defer, never prompt)

When run headless (the cloud routine) or in batch, the extractor's normal
in-run check-ins **cannot be answered**. So in this mode:

- **Never block on a question.** Any unknown/uncertain alias, proposed new metric type, or
  ambiguous format is written into `<slug>_review.md` under a **"HUMAN DECISION NEEDED"**
  heading as an unchecked `- [ ]` item.
- Leave `- [ ] Checkpoint: approved for export` **unchecked**. The export gate in
  `export.py` then correctly refuses until a human resolves the items and signs off.
- This is by design and compliance-required: the routine takes data *to* the gate, never *through* it.

## Boundaries

- Does **NOT** write to the Epidemiology Master Sheet (that is the exporter).
- Does **NOT** cross or auto-approve the checkpoint (that is a human, via the pipeline).
- Does **NOT** reimplement extraction — it invokes `pharma-epi-extractor`.
- Fetches third-party documents only; flags "needs manual pull" rather than guessing.

## Edge Cases

- **DNS/host quirks** — `fetch.py` retries `media.*` → `www.*`; if a host still fails, the source is reported failed (not silently skipped).
- **Sparse/absent series** — a company may lack a standalone epi report (e.g. Sanofi); register those as `one_off` entries as found.
- **Renamed files** — GSK Q1 2023 is `-epidemiology-data.xlsx`, not `-report`; that's why `link_match` is a substring, not a filename.
- **Content dedup** — if the same bytes reappear under a new URL, sha256 dedup skips it.

## Compliance

Everything pulled here is third-party source material feeding AI-generated
research: independently verify before use, never the sole basis for a decision,
retain per RAC recordkeeping (see `reference/pipeline.md`). Check third-party
documents for **AI-usage restrictions** before ingesting (uncertain →
legal@racap.com / thecompliancecrew@racap.com). Any **Box app token is a secret** —
env var only, never committed or written into these skill files.
