---
name: pharma-epi-exporter
description: >-
  Export skill that writes the pharma-epi-extractor's staging output into the
  Epidemiology Master Sheet. Consumes the extractor's *_granular.csv,
  *_sheet1.csv (and optional *_aliases.csv) plus the *_review.md sign-off note,
  appends the rows to a LOCAL copy of the master workbook (Granular Data tab,
  Sheet1 tab, Indication Aliases tab) with the correct number formats and
  uncertain/known-wrong flag fills, and produces an *_UPDATED.xlsx for the user
  to review and upload to Box. Use after the extractor has run and the review note is signed
  off, or when the user says "export this", "write it to the master sheet",
  "push the staged data", or "load the staging CSVs into the workbook".
version: 1
---

# pharma-epi-exporter

## What This Skill Does

Takes the staging files produced by `pharma-epi-extractor` for one source and
appends them into the **Epidemiology Master Sheet** (`.xlsx`), preserving the
workbook's existing tabs, rows, formulas, and formatting. It is the second half
of the pipeline; it does no extraction, classification, or alias matching of its
own — those are settled by the extractor before this runs.

It does **not** reshape data. The granular CSV is already 1:1 with Granular Data
columns A–P and the Sheet1 CSV is already 1:1 with Sheet1 columns B–I; this skill
just places those rows after the last existing row and applies formats.

> **Pipeline reference:** `../pharma-epi-extractor/reference/pipeline.md` is the
> single source of truth for the definition of done, the flag legend, the full
> target schema, the Box constraint, and the investment-use/recordkeeping
> reminder. This SKILL covers only the exporter's own steps.

## The Box Constraint (read this first)

The Box MCP tools in this environment are **text-only**: `get_file_content`
returns a text extraction (not the real binary), and `upload_file` /
`upload_file_version` accept text content only (binary upload needs
`get_upload_url`, which is not available here). **You cannot round-trip a binary
`.xlsx` through Box.** Therefore the export runs against a **local copy** of the
master workbook and produces a local `*_UPDATED.xlsx`. The user uploads that file
to Box as a new version themselves. Never claim to have written to Box.

If the user has not provided a local copy of the master workbook, **ask them to
drop the current `Epidemiology Master Sheet.xlsx` into the working directory**
(default `/Users/mattsanders/Documents`). Do not try to reconstruct it from the
text extraction — that loses formatting, formulas, and the other tabs.

## Inputs

For source slug `<slug>` — the staging **CSVs** live in
`/Users/mattsanders/Documents/CSV Archive/` (user preference, 2026-07-01); the
`<slug>_review.md` sign-off note lives in `/Users/mattsanders/Documents`:

1. `<slug>_granular.csv` — header 1:1 with Granular Data A–P (16 columns).
2. `<slug>_sheet1.csv` — header 1:1 with Sheet1 B–I (8 columns), one data row.
3. `<slug>_review.md` — the human-checkpoint note. **Read it first.** Passed to
   `export.py --review`; a real export is blocked unless it carries a checked
   `- [x] Checkpoint: approved for export` line and no open `- [ ]` items.
4. `<slug>_aliases.csv` *(optional)* — approved new alias rows
   (`Canonical Indication Name,Therapeutic Area,Known Aliases`), written by the
   extractor whenever a new canonical term was approved. Consume it directly; do
   not re-derive aliases from the review note. Absent → no new aliases this run.
5. A local copy of `Epidemiology Master Sheet.xlsx`.

## Workflow

**Step 1 — Checkpoint gate (mechanically enforced).** Read `<slug>_review.md`. If
it contains unresolved items — open questions ("please confirm"), deferred rows,
ambiguous metric classifications, or anything under "Not determinable" that
affects a row being exported — **stop and surface them to the user.** Do not
export until they are signed off. This is the human checkpoint; the exporter must
not paper over it.

This gate is **enforced in `export.py`, not honor-system**: a real (non-`--dry-run`)
run requires `--review <slug>_review.md`, and the note must carry the exact line

```
- [x] Checkpoint: approved for export
```

with **no remaining unchecked `- [ ]` items**. Without the checked line the export
is blocked; with the line but an open `- [ ]` item it is blocked as inconsistent.
There is no CLI override — the human must check the box. `--dry-run` skips the gate
(it writes nothing). The extractor seeds the note with an unchecked
`- [ ] Checkpoint: approved for export`; the human flips it to `[x]` only after
every open item is resolved.

**Step 2 — Confirm the workbook.** Locate the local master `.xlsx`. If absent,
ask the user to provide it (see The Box Constraint). Confirm the three target
tabs exist: `Granular Data`, `Sheet1`, `Indication Aliases`.

**Step 3 — Dry run.** Run `export.py --dry-run` to report where rows will land
(target rows, flag-fill counts, alias placement) without writing. Show the user.

**Step 4 — Write the local copy.** Run `export.py` without `--dry-run`, passing
`--review <slug>_review.md` (the gate from Step 1 must pass) and
`--out` with the **house filename convention** (see `reference/pipeline.md`):
`Epidemiology Master Sheet (DD Month YYYY, H:MMam/pm).xlsx` (day no leading zero,
full month, lowercase am/pm, no space) stamped with the current date/time. Each
run is a new timestamped file, not an overwrite. The source is left untouched.
Pass `--link-data` if the user has the source document's Box URL for the Sheet1
row. (Without `--out` the script falls back to `<workbook>_UPDATED.xlsx`; prefer
the stamped name.)

**Step 5 — Verify (see Post-Export Verification) and hand off.** Tell the user
the updated file path and that they should review it and upload it to Box as a
new version of the master sheet. Remind them of the recordkeeping note.

## Running the helper

```
python3 export.py \
  --workbook "/Users/mattsanders/Documents/Epidemiology Master Sheet.xlsx" \
  --granular "/Users/mattsanders/Documents/CSV Archive/<slug>_granular.csv" \
  --sheet1   "/Users/mattsanders/Documents/CSV Archive/<slug>_sheet1.csv" \
  --review   "/Users/mattsanders/Documents/<slug>_review.md" \
  [--aliases "/Users/mattsanders/Documents/CSV Archive/<slug>_aliases.csv"] \
  [--link-data "https://racap.app.box.com/file/<id>"] \
  [--out "/path/out.xlsx"] [--dry-run]
```

Requires `openpyxl`. The script fails loud (non-zero exit, clear message) if a
tab is missing, a CSV has the wrong column count, or a numeric column holds a
non-number. A real (non-`--dry-run`) export also fails loud if `--review` is
missing or its note lacks the checked `- [x] Checkpoint: approved for export`
line (or still has open `- [ ]` items) — see Step 1.

## Target Schema (must match the workbook)

**Granular Data** — data starts in column **A**, no spacer. CSV cols 1–16 →
sheet cols A–P:

| Col | Header | Notes |
|-----|--------|-------|
| A | Source | constant per source |
| B | Company | constant per source |
| C | Disease Area | matched TA |
| D | Original Indication Label | |
| E | Indication (Standardized) | |
| F | Original Metric Label | |
| G | Metric Type (Standardized) | |
| H–L | US, EU5, China, Japan, Total | integer `#,##0`; empty if not reported |
| M | Geography | |
| N | Data Year | |
| O | Projection / Methodology Note | |
| P | Data Quality Notes | carries the flag token (`flag:uncertain` / `flag:red`) |

**Sheet1** — column **A is a blank spacer** (header in row 2); the **8** staging
fields map to **B–I**: Source Overview (B), Disease Area(s) (C), Indication (D),
Metrics (E), Geography (F), Link to data (G), Description/Considerations/
Limitations (H), Underlying Data Sources (I). There is no companion-doc column.
Append as one new row.

**Indication Aliases** — data starts in column **A**: Canonical Indication Name
(A), Therapeutic Area (B), Known Aliases (C). New approved rows only.

## Formatting Rules

New rows are styled to match the existing rows on each tab — the script does not
leave them with default formatting.

- **H–L** are written as integers with number format `#,##0` (no text, no commas
  in the stored value).
- **Granular Data** new rows take Arial 10, wrapped, top-aligned, row height 28,
  and continue the tab's zebra banding (even sheet row → light blue `FFEBF3FB`,
  odd → white). A flag fill overrides the band on the affected cell.
- **Flag fills (two colors — see the legend in `reference/pipeline.md`):** the
  script reads the flag token in the Data Quality Note (col P) and paints in one
  pass. `flag:uncertain` → `FFD966` on the populated numeric cell(s) (soft/
  averaged/midpoint/inferred value). `flag:red` → standard red `FFFF0000` on the
  Total cell (col L) for a known-wrong value (e.g. Total ≠ sum of geographies).
  The note text is preserved in column P.
- **Sheet1** new rows clone the style (font, borders, alignment, row height) of
  the last existing data row, so they match even past the workbook's
  pre-formatted zone.
- Empty geography cells stay empty — never spread one figure across columns or
  write 0.

## Indication Aliases — sorted, color-coded insertion

The Aliases tab is grouped by Therapeutic Area: each group is a dark-blue bold
header row (`FF2E75B6`, white text, height 20) followed by data rows in a
**group-specific pastel fill** (Arial 10, height 30). The script **inserts** each
new alias into the matching TA group at the correct **alphabetical** slot (by
Canonical Indication Name), applies that group's fill/font/height, and re-asserts
all header (20) / data (30) row heights afterward (openpyxl `insert_rows` shifts
cells but not row-height definitions). No manual repositioning needed.

- **TA match** is case-insensitive against the group-header text.
- **New TA group:** if the alias's TA has no existing group, the script appends a
  new header row + the data row at the bottom with a placeholder fill
  (`FFF2F2F2`) and **warns** — verify the group's position and color manually.
- Existing groups in the live sheet may not be strictly alphabetical; new rows are
  placed alphabetically regardless, so a new row can sit between unsorted
  neighbors. That is expected and honors the tab's "HOW TO USE" instruction.

## Post-Export Verification

- Granular row count appended = data rows in the granular CSV.
- Spot-check that H–L values landed in the right columns and show `#,##0`.
- Every `flag:uncertain` row has the FFD966 fill on its numeric cell(s); every
  `flag:red` row has red on its Total cell. Counts match the script's report.
- The Sheet1 summary row is in column B onward (column A still blank), styled to
  match existing rows (borders/font/height).
- Granular new rows continue the zebra banding and use Arial 10 / wrap / height 28.
- Each new alias sits inside its TA group with the group's fill; header/data row
  heights are 20/30; any new TA group is flagged for manual color/position check.
- Other tabs, existing rows, and formulas are unchanged (the script edits a copy;
  alias inserts shift rows within the Aliases tab only).
- Remind the user: review, then upload `*_UPDATED.xlsx` to Box as a new version;
  retain per recordkeeping policy.

## Edge Cases

- **No granular rows (summary-only source):** still append the Sheet1 row; report
  0 granular rows.
- **Missing local workbook:** ask for it; do not reconstruct from text.
- **Unresolved review items:** stop at Step 1; export nothing until signed off.
- **Link unknown:** leave the Link-to-data cell (G) blank (the script notes
  this); fill later via `--link-data`.
