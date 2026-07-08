# Pharma-Epi Pipeline — shared reference (single source of truth)

This file is the canonical reference for all three pharma-epi skills
(`pharma-epi-extractor` → `pharma-epi-exporter` → `pharma-epi-qc`). Schema,
flag legend, the success definition, and the handoff rules live **here only**;
the individual SKILL.md files point to this file rather than restating it.
When the workbook layout changes, update this file (and the code constants in
`export.py` / `qc.py`) — not three separate prose copies.

> **Investment-use (org rule):** pipeline output is investment-research data —
> independently verify before use, never the sole basis for a decision, retain
> per RAC recordkeeping. Don't move confidential/MNPI content outside RAC
> systems without Compliance approval.

## Definition of done (what success looks like)

The pipeline succeeds, end to end, when:

1. **Extract** — the right read method (adapter or generic) is selected; every
   patient-population number is captured (revenue/share/pricing/enrollment
   ignored); each is mapped to a canonical indication + therapeutic area +
   metric type; same indication across years is kept **as-reported each year**
   (longitudinal, never deduped/reconciled). Output: staging CSVs
   (`_granular`, `_sheet1`, and `_aliases` when new terms were approved) plus a
   review note listing only what needs sign-off. *Or* a clean "no usable epi
   data" verdict.
2. **Checkpoint (gate)** — you sign off the review note. No sign-off → no export.
   This is **mechanically enforced**: the extractor seeds the note with an
   unchecked `- [ ] Checkpoint: approved for export` line; `export.py --review`
   refuses a real (non-`--dry-run`) write unless that line is checked `[x]` and no
   other `- [ ]` items remain. There is no CLI override.
3. **Export** — rows land in the right columns/formats; flags applied by the
   script in one pass; new aliases inserted into the correct TA group; existing
   rows/formulas/tabs untouched → a local output workbook handed to you to
   upload to Box (the skills never write to Box). The output is named per the
   **house filename convention** (see below), not left as `*_UPDATED.xlsx`.
4. **QC** — `qc_report.md` shows indications → canonical, TA consistent, metric
   types in taxonomy, Total ≈ sum; new exceptions are surfaced and fixed, then
   QC re-runs clean.
5. **Close-out** — verify/recordkeeping reminder given; confirmed flags cleared
   (flag-clearing is a tracked follow-up, not yet automated).

## The two interactive surfaces (don't double-handle)

There are two distinct places you get involved; they are **not** redundant:

- **In-extractor check-in (during the run)** — for items that *block an output
  cell*: an uncertain alias, a missing term, or a new metric type. The extractor
  cannot fill the standardized column without your answer, so it asks then. This
  is what lets it honor "never guess."
- **Checkpoint gate (between extract and export)** — a final go/no-go on the
  finished batch. It also covers items that *don't* block a cell (flagged
  values, arithmetic discrepancies, limitations).

**Boundary rule:** the extractor asks during the run **only** for blocking
items. The review note then **records those decisions as settled** (a
confirmation surface), so the checkpoint is a fast "yes, approved" — not a
re-ask. Non-blocking items live only in the review note and are resolved at the
checkpoint.

## Flag legend (two colors)

| Flag | Meaning | DQ-note token | Fill | Applied to |
|---|---|---|---|---|
| **Uncertain / soft** | the number or classification is soft | `flag:uncertain` | `FFD966` | the populated numeric cell(s) |
| **Known-wrong** | internal contradiction / definite error | `flag:red` | standard red `FFFF0000` | the Total cell |

- **Uncertain** covers averaged/midpoint patient counts, ranges, inferred metric
  types, and chart-only reads. (This merges the former "amber" and "orange".)
- **Known-wrong** is primarily Total ≠ sum of geographies (material, >0.5%).
- The token goes in the Data Quality Notes cell (col P); `export.py` reads it and
  paints the fill in one pass — no manual coloring.
- Once a flagged cell is reviewed/confirmed, the flag is removed (the note may
  stay). *(Clearing is a planned follow-up step.)*

## Target schema (verify against the live workbook before relying on it)

The master workbook (Box file 2293926664026) currently has **4 tabs**.

### Granular Data — one row per data point, data begins in col **A** (no spacer)

| Col | Header | Notes |
|---|---|---|
| A | Source | constant per source |
| B | Company | constant per source |
| C | Disease Area | matched therapeutic area |
| D | Original Indication Label | |
| E | Indication (Standardized) | |
| F | Original Metric Label | |
| G | Metric Type (Standardized) | |
| H–L | US, EU5, China, Japan, Total | integer `#,##0`; empty if not reported |
| M | Geography | free-text scope label |
| N | Data Year | |
| O | Projection / Methodology Note | |
| P | Data Quality Notes | carries the flag token |

`Total` is the source's stated total (don't compute unless the source omits it —
and flag if you do). Never spread one regional figure across columns; empty cell
where a geography isn't reported, never 0.

### Sheet1 — one summary row per source; col **A is a blank spacer**

Header is in **row 2**; the **8** staging fields map to cols **B–I**:

| Col | Field |
|---|---|
| B | Source Overview |
| C | Disease Area(s) |
| D | Indication |
| E | Metrics |
| F | Geography |
| G | Link to data |
| H | Description, Considerations, Limitations |
| I | Underlying Data Sources |

(The former "Link to companion doc" column was removed — there is no companion-doc
column.) Leave the Link-to-data cell blank in the CSV; the exporter wires it via
`--link-data`.

### Indication Aliases — canonical lookup (the extractor owns this)

Row 1 = column headers; row 2 = a HOW-TO instruction row; then **TA-grouped**:
each group is a bold dark-blue header row (col A = TA name, col B empty) followed
by data rows. Three columns: **A** Canonical Indication Name · **B** Therapeutic
Area · **C** Known Aliases (comma-separated). Read it live at the start of every
run; it fills both `Indication (Standardized)` and `Disease Area`.

### Metric Type Aliases — canonical metric taxonomy (source of truth)

Row 1 = headers; row 2 = HOW-TO; data rows 3+: **A** Canonical Metric Type ·
**B** Definition · **C** Known Source Labels. `qc.py` reads col A of this tab to
build the valid metric-type set, so the taxonomy is **defined once here** — no
hardcoded list to keep in sync. The current 7 types: Total Prevalence,
Diagnosed Prevalence, Treated Prevalence, Addressable/Eligible Population,
Incidence, Treatment Utilization, At-Risk Population. The taxonomy is
**extensible**: an approved new type is added to this tab (and it flows to QC
automatically).

## The Box constraint

Box MCP tools here are **text-only**: `get_file_content` returns a text
extraction (not the binary), and uploads accept text only. You **cannot
round-trip a binary `.xlsx` through Box.** So export/QC run on a **local copy**
of the workbook; the exporter writes a local output workbook and the user
uploads it to Box as a new version. Never claim to have written to Box.

## House filename convention (every new workbook)

Every time a skill produces a new version of the workbook — the exporter's
output, or a QC fix-application pass — **stamp the file with the current date
and time** in this exact format, rather than leaving a generic suffix:

```
Epidemiology Master Sheet (DD Month YYYY, H:MMam/pm).xlsx
```

- **DD** — day of month, **no leading zero** (e.g. `5`, not `05`).
- **Month** — full month name (`June`, not `Jun` or `06`).
- **H:MM** — 12-hour clock, no leading zero on the hour (e.g. `9:53`, `1:42`).
- **am/pm** — lowercase, **no space** before it (`953am` style → `9:53am`).

Examples: `Epidemiology Master Sheet (24 June 2026, 10:42am).xlsx`,
`Epidemiology Master Sheet (30 June 2026, 2:15pm).xlsx`.

This is a per-edit policy: each new output is a **new timestamped file**, not an
overwrite/retitle of the prior one, so the version history is preserved. (The
exporter's `--out` flag and the QC fix pass both take this name explicitly.)
