---
name: pharma-epi-pipeline
description: >-
  End-to-end orchestrator that runs the full epidemiology-ingestion workflow as ONE
  flow: extract a pharma source document, pause once for the human checkpoint sign-off,
  then automatically export into the Epidemiology Master Sheet and automatically run QC.
  Use when the user wants to take a pharma PDF/Excel all the way into the master sheet in
  a single pass, or says "run the whole pipeline", "ingest this end to end", "extract and
  load this into the master sheet", "do the full epi workflow", or "run the pharma-epi
  pipeline". This is the single entry point that wraps pharma-epi-extractor,
  pharma-epi-exporter, and pharma-epi-qc and chains them in order — the export and QC
  stages run without asking; the only human touchpoints are unknown-alias decisions during
  extraction and the mandatory checkpoint sign-off (a hard, code-enforced gate that must
  not be auto-approved).
version: 1
---

# pharma-epi-pipeline

One skill that runs the whole epidemiology-ingestion pipeline in the correct order.
It **orchestrates** the three component skills — it does not reimplement them:

```
pharma-epi-extractor  →  [CHECKPOINT sign-off]  →  pharma-epi-exporter  →  pharma-epi-qc
       (Stage 1)              (Stage 2)                  (Stage 3)            (Stage 4)
```

**What runs automatically (no asking):** the transitions between stages, the export
(dry-run preview then the real gated write), and the QC audit at the end. Do **not**
stop to ask "shall I proceed to export?" or "want me to run QC?" — chain them.

**The only two human touchpoints — never skip either:**
1. **Unknown / uncertain indication aliases or new metric types during extraction.**
   The extractor must never invent a canonical name or a metric type. Batch every such
   question into **one consolidated ask** (see Stage 1), then continue.
2. **The checkpoint sign-off (Stage 2).** This is a hard gate enforced in
   `export.py` (there is no CLI override) and required by RAC compliance — AI-extracted
   data may not enter the investment master without a human verifying it. **You may not
   auto-check the box.** Present a tight go/no-go and wait for the human to approve.

## Prerequisites

- The three component skills are installed as siblings in the same skills directory:
  `pharma-epi-extractor/`, `pharma-epi-exporter/`, `pharma-epi-qc/` (they ship together
  in the pipeline bundle). Resolve their paths relative to the skills directory that
  holds this skill (e.g. `<skills>/pharma-epi-exporter/export.py`).
- `openpyxl` installed (`pip install openpyxl`).
- A **local copy** of the master `Epidemiology Master Sheet (…).xlsx` in the working dir
  (Box is text-only here; the export edits a local copy — see the exporter's Box note).
- Access to the master's live **Indication Aliases** / **Metric Type Aliases** tabs
  (Box file 2293926664026) for alias/metric resolution and QC.

## Stage 1 — Extract (interactive only for aliases)

Follow **`pharma-epi-extractor/SKILL.md`** exactly, including its adapter selection
(`pharma-epi-extractor/adapters/INDEX.md` first — route by container × representation)
and the **Visual read** fallback for rasterized content. Produce the staging CSVs
(`<slug>_granular.csv`, `<slug>_sheet1.csv`, optional `<slug>_aliases.csv` in
`~/Documents/CSV Archive/`) and the `<slug>_review.md` note in `~/Documents/`.

- Resolve every indication/metric against the live tabs. **Collect all uncertain or
  missing aliases and any proposed new metric type into a single batched question** and
  ask the user once, rather than interrupting repeatedly. Apply their answers, write any
  approved new terms to `<slug>_aliases.csv`.
- Emit the review note ending with the unchecked
  `- [ ] Checkpoint: approved for export` line. Do **not** pre-check it.

## Stage 2 — Checkpoint (the one mandatory pause)

Present a concise go/no-go to the user drawn from the review note:
- source recap (1 line), row count, TAs touched, any **new TA** to be created;
- the flagged rows that need a human eye (uncertain / source-inconsistent);
- new canonical aliases / metric types approved this run.

Then **wait for the human to sign off** — i.e. flip the note's last line to
`- [x] Checkpoint: approved for export` with no other open `- [ ]` items. Do not proceed
to Stage 3 until that is done. (If the user explicitly signs off in chat, you may flip the
box on their behalf per their instruction, but the human must make that call — never
auto-approve unprompted.)

## Stage 3 — Export (automatic once signed off)

Run **`pharma-epi-exporter`**'s helper. No need to ask permission — the sign-off in
Stage 2 is the authorization.

1. **Dry run** (report placement, flag-fill counts, alias/new-TA plan):
   ```
   python3 <skills>/pharma-epi-exporter/export.py \
     --workbook "<local master>.xlsx" \
     --granular "~/Documents/CSV Archive/<slug>_granular.csv" \
     --sheet1   "~/Documents/CSV Archive/<slug>_sheet1.csv" \
     --review   "~/Documents/<slug>_review.md" \
     [--aliases "~/Documents/CSV Archive/<slug>_aliases.csv"] \
     --dry-run
   ```
2. **Real write** — same command without `--dry-run`, plus `--out` using the house
   filename convention `Epidemiology Master Sheet (DD Month YYYY, H:MMam/pm).xlsx`
   (day no leading zero, full month, lowercase am/pm, no space), stamped now. The
   `--review` gate must pass (it will, given Stage 2). Add `--link-data <box-url>` if the
   source's Box URL is known.

Surface the exporter's warnings verbatim — in particular a **new-TA-group** warning means
the group was appended at the bottom with a gray placeholder fill and needs a manual
color/position fix. Report it; it is expected, not an error.

## Stage 4 — QC (automatic)

Immediately run **`pharma-epi-qc`** on the file just written — do not ask:
```
python3 <skills>/pharma-epi-qc/qc.py "<the --out file>.xlsx" --out "~/Documents/<slug>_qc_report.md"
```
Read the report and summarize for the user: Tier-1 (indication/TA) pass/fail, metric-type
checks, and any Total≠sum rows — **distinguishing newly-added rows from pre-existing
ones** (only new-row issues are actionable this run). Known benign false-positives
(tiered ophthalmology labels like `'Prevalence (existing cases)'`; `'Treated population'`
mapping to more than one tier) should be called out as expected, not raised as errors.

## Final hand-off

Tell the user: the updated workbook path, the QC summary, any manual touch-up (new-TA
color/position), and that they should review it and upload it to Box as a new version.

## Failure handling

- **Gate blocks the export** (no `- [x]` line, or an open `- [ ]` remains): stop, report
  which condition failed, and return to Stage 2. Never bypass with `--dry-run` to fake a
  write, and never edit the gate.
- **Missing local workbook:** ask the user to drop the current master `.xlsx` in the
  working dir (do not reconstruct from a Box text extraction).
- **A component skill isn't installed:** tell the user which sibling folder is missing.
- **Extraction finds no epi data:** stop after Stage 1, write the "no epi data" review per
  the extractor, and skip Stages 3–4.

## Compliance (RAC)

AI-generated extractions must be independently verified before any investment use, may not
be the sole basis for a decision, and are retained per RAC recordkeeping. The Stage 2
human checkpoint is how that verification is enforced — it exists precisely so this
otherwise-automatic pipeline cannot push unverified data into the master. Check any
third-party source document for AI-usage restrictions before ingesting
(legal@racap.com / thecompliancecrew@racap.com if unsure).
