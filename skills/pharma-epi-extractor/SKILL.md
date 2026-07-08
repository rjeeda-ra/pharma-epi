---
name: pharma-epi-extractor
description: >-
  Analysis skill that scrapes and structures epidemiology (patient population)
  data from a single pharma source document (earnings deck, pipeline event,
  standalone epi report, R&D day) ahead of ingestion into the Epidemiology
  Master Sheet. Use when a user uploads a pharma PDF/Excel and asks about epi
  data, what indications/geographies a source covers, whether a source is worth
  ingesting, or asks to "pull the epi data" / "summarize this for the database"
  / "can we use this source". Produces export-ready staging CSVs plus a short
  review note flagging anything uncertain. Does NOT write to the spreadsheet —
  that is the pharma-epi-exporter skill's job.
version: 3
---

# pharma-epi-extractor

## What This Skill Produces

For a **single** pharma source document, the extractor produces two things:

1. **Staging CSVs** — the primary artifact and source of truth for the data.
   A granular CSV (one row per data point, columns mapped 1:1 onto the Granular
   Data tab A–P) plus a one-row Sheet1 CSV. The downstream
   `pharma-epi-exporter` skill consumes these with no reshaping.
2. **A short "Needs review" note** (Markdown) — text reserved *only* for items
   requiring your sign-off at the human checkpoint: alias decisions, uncertain
   (e.g. range→midpoint) rows, source arithmetic discrepancies, chart-only reads,
   and anything not determinable. Clean rows generate no prose.

Both are written locally (never to Box). **Staging CSVs go to
`/Users/mattsanders/Documents/CSV Archive/`** (user preference, 2026-07-01 — keeps
the CSVs out of the Documents root); the **review note (`*_review.md`) stays in
`/Users/mattsanders/Documents`** (it is the human-facing sign-off/audit artifact).
The exporter reads the staging CSVs from `CSV Archive/`. This skill never writes to
the spreadsheet — extraction and export are separate, with a human checkpoint
between them (owned by the `pharma-epi-pipeline` wrapper).

> **Investment-use & pipeline reference:** see `reference/pipeline.md` for the
> shared definition of done, the interactive-surface boundary rule, the flag
> legend, the full target schema, and the investment-use/recordkeeping reminder.
> That file is the single source of truth for anything shared across the three
> skills; this SKILL covers only the extractor's own steps.

## Trigger Conditions

- User uploads a pharma PDF/Excel and asks about epi data
- "What indications does this cover", "what geographies", "can we use this for
  the database", or similar
- User wants to assess whether a new source is worth ingesting
- Phrases like "what epi is in this", "pull the epi data", "summarize this for
  the database", "can we use this source"

## Target Schema (Epidemiology Master Sheet)

The full column layout for all four tabs lives in `reference/pipeline.md` — read
it (and verify against the live workbook) rather than relying on a copy here.
Extractor-relevant essentials:

- **Granular Data** maps 1:1 onto sheet cols **A–P** (data begins col A, no
  spacer). H–L (US/EU5/China/Japan/Total) are integers; `Total` is the source's
  stated total (don't compute it unless the source omits it — and flag if you do).
- **Sheet1** is **8 fields → cols B–I** (col A blank, header in row 2); there is
  no companion-doc column.
- **Indication Aliases** is the canonical lookup (Canonical Indication Name ·
  Therapeutic Area · Known Aliases). **The extractor owns this lookup** — read the
  live tab from the master workbook (Box file 2293926664026) at the start of every
  run and use it to fill both `Indication (Standardized)` and `Disease Area`. See
  "Alias Matching" below.

## Output Format

The extractor writes the **staging CSVs** (the data) and **one Markdown review
note** (only the items needing sign-off). Name files with a source slug, e.g.
`gsk-q1-2026_granular.csv`, `gsk-q1-2026_sheet1.csv`, and `gsk-q1-2026_review.md`
— plus `gsk-q1-2026_aliases.csv` **whenever any new canonical term was approved
this run** (3 columns: Canonical Indication Name, Therapeutic Area, Known
Aliases). The exporter consumes that CSV directly — do not make it re-derive
aliases from the review note. If a field can't be determined, leave the cell
empty and note it in the review note — never guess.

### A. Granular staging CSV — primary artifact

Header row, columns 1:1 with Granular Data A–P (no blank spacer column):

```
Source,Company,Disease Area,Original Indication Label,Indication (Standardized),Original Metric Label,Metric Type (Standardized),US,EU5,China,Japan,Total,Geography,Data Year,Projection / Methodology Note,Data Quality Notes
```

Row rules:
- One row per (indication × metric type × geography-set) data point. Record
  prevalence and diagnosed as **separate rows** when both appear.
- Put numbers in the correct US/EU5/China/Japan columns. Leave a cell **empty**
  if that geography isn't reported; never spread one regional figure across
  columns. US/EU5/China/Japan/Total are plain integers — no thousands
  separators, no quotes, no text in those cells.
- If only a single combined figure is given (e.g. "Global", "US only"), put it
  in `Total` (or the one applicable column) and describe scope in `Geography`.
- `Source` and `Company` are constant — repeat them on every row.
- **Flags (two colors — see the legend in `reference/pipeline.md`):** put a token
  in `Data Quality Notes` and the exporter paints the fill in one pass.
  - **Uncertain/soft value** (range→midpoint, averaged count, inferred metric,
    chart-only read): record the value and add `flag:uncertain` plus a short
    reason, e.g. `range X–Y; midpoint shown — flag:uncertain`. → FFD966 on the
    populated numeric cell(s).
  - **Known-wrong** (e.g. stated Total ≠ sum of geographies): keep the source
    figures as-is and add `flag:red` plus the reason. → red on the Total cell.
  Also list any flagged row in the review note.
- `Indication (Standardized)` / `Disease Area`: resolved via the Alias Matching
  rules below. By the time the CSV is written these are settled — anything you
  couldn't resolve confidently was asked about during the run.
- `Data Quality Notes`: `OK` for clean rows; otherwise a specific flag. Quote
  any field that contains a comma.

### B. Sheet1 staging CSV — one summary row for the source

Header 1:1 with the Sheet1 tab (**8 fields → cols B–I**; there is no
companion-doc column):

```
Source Overview,Disease Area(s),Indication,Metrics,Geography,Link to data,"Description, Considerations, Limitations",Underlying Data Sources
```

- `Disease Area(s)`: `Multiple`, or the single TA.
- `Indication`: comma-separated list of indications with data.
- `Metrics`: one metric type per line — `Metric Type — "example label" (indications)`.
- `Geography`: all geographies with numeric data.
- `Description, Considerations, Limitations`: a tight paragraph covering 3–6
  specific limitations — always address metric-definition consistency, geography
  scope, data year, source transparency, and indication caveats. No boilerplate.
- Leave the `Link to data` column empty (the exporter wires it via `--link-data`).

### C. Review note (Markdown) — human checkpoint surface

Only what you need to sign off on. Sections:

1. **Source recap** — document type, company, date/period, primary purpose, epi
   data present (Yes/No/Partial), reference year, and whether figures are
   projections or actuals (e.g. GSK projects to 2030; NVS anchors to a stated
   actual year). One short block.
2. **Alias decisions** — every match that was *not* a confident exact/known-
   alias hit: original label from the report → resolved canonical (+ TA), and
   how it resolved (your answer, or a new term you approved). List approved new
   terms separately so the exporter knows to append them to the Aliases tab.
3. **Flagged rows** — each granular CSV row carrying a non-`OK` Data Quality
   Note: `flag:uncertain` (midpoint/averaged/inferred/chart-only) or `flag:red`
   (arithmetic discrepancy), plus mixed metric definitions. Reference the row.
4. **Not determinable** — any field you couldn't establish, and why.
5. **Checkpoint marker (required, last line).** End the note with the unchecked
   sign-off line, verbatim:

   ```
   - [ ] Checkpoint: approved for export
   ```

   The exporter's `export.py --review` refuses a real write until a human flips
   this to `- [x]` *and* no other `- [ ]` items remain open. Emit it unchecked on
   every note; never pre-check it yourself. If you list open questions as `- [ ]`
   items elsewhere in the note, those must also be checked before export.

## Source Adapters (the bundled reading-method library)

Different sources lay out epi data very differently — a GSK epidemiology
workbook is a clean one-row-per-point table, a Roche epi-master PDF is
three-column text, a slide deck buries numbers in stacked bar charts. The
per-source reading methods ("adapters") live in the **`adapters/` folder bundled
inside this skill** (so they travel with it), one guide per source type. They
are lazy-loaded — only this `SKILL.md` auto-loads; a guide is read only when
selected — so the library can grow without bloating the skill:

```
adapters/
  INDEX.md              # registry + selector — READ THIS FIRST
  <source>.md           # one reading guide per source type
```

**Access + select procedure** (do this before the generic Step 1 scan):

1. **`Read` `adapters/INDEX.md`.** It holds the Selector and the routing logic.
2. **Route by *representation*, not company.** The reading method is determined
   by how the numbers are physically encoded, in two parts: **container** (.xlsx
   → cell reads; PDF/deck → pdfplumber) × **representation** (structured cells /
   positioned text / chart-graphic / narrative). One company can ship several
   formats — e.g. Roche has both a positioned-text PDF and a bar-chart deck — so
   the on-page layout decides, never the company name alone. Use INDEX.md's
   Selector + Disambiguation notes.
3. If a guide matches, **`Read` that guide file** and follow it **in place of**
   the generic Step 1–2 scan. Then continue the shared Steps 3–6 below
   (source-agnostic).
4. If **no guide matches**, use the generic Step 1–2 scan. Once that source
   proves recurring and worth standardizing, **author a new guide in `adapters/`**
   (INDEX.md → "Adding a guide") and add a Selector row — never bake a new
   reading method into this SKILL.md.

## Extraction Process

**Step 1 — Document scan.** Read the full document. Identify every
slide/table/section with a **patient population number**.
*Explicitly ignore:* revenue/sales figures, market share %, pricing, clinical
trial enrollment counts, and addressable-market dollar figures. These are not
epi data.

**Step 2 — Indication inventory.** For each population number capture: indication
name (source language), metric label (exact words), numeric value(s), geography,
year. Record prevalence AND diagnosed separately when both appear. Keep regional
figures in their own buckets.

**Step 3 — Metric classification.** Map each label to the standardized taxonomy
(below). Apply conservative interpretation for ambiguous labels and flag in the
Data Quality Note for that row. If a label genuinely does not fit any of the
existing types, do **not** force-fit it — follow the *New Metric Type* rule in
the taxonomy section (stop and ask before adding an 8th+ type).

**Step 4 — Source check.** Look for footnotes, citations, and methodology notes.
Note whether figures are company-internal, consensus-based, or from named third
parties (DRG, Kantar, IQVIA, Evaluate Pharma, academic citations, etc.). Capture
projection vs. actual basis here too — it feeds the Projection / Methodology
Note column.

**Step 5 — Resolve aliases (interactive).** Run every indication and TA through
the Alias Matching rules below, pausing to ask whenever a match is uncertain or
the term is missing from the sheet. Resolve all of these before writing files.

**Step 6 — Write outputs.** Populate the granular staging CSV and the Sheet1
staging CSV, then write the review note covering only the items needing
sign-off. Be specific — real indications, geographies, numbers.

## Alias Matching

The extractor resolves every indication and therapeutic area against the live
**Indication Aliases** tab (read it from Box file 2293926664026 at the start of
the run). For each source term:

1. **Confident match** — the source label equals a Canonical Indication Name or
   appears in that row's Known Aliases (case- and punctuation-insensitive). Fill
   `Indication (Standardized)` with the canonical name and `Disease Area` with
   that row's Therapeutic Area. No need to ask.
2. **Uncertain match** — a plausible but not exact/known-alias candidate (a
   wording variant, a subtype ambiguity, or more than one possible canonical).
   **Stop and ask.** Show the original label from the report and the candidate
   canonical name(s) + TA, and let the user pick or correct.
3. **No match** — the term isn't in the sheet at all. **Ask before adding it to
   the chart.** Tell the user the term as written in the report and the TA
   grouping the report places it under, and propose a new canonical name +
   Therapeutic Area if you have a suggestion. Only after the user approves do you
   (a) use it in the CSV and (b) record the approved new alias row in the review
   note so the exporter can append it to the Indication Aliases tab.

Never silently invent a canonical name or TA. When in doubt, ask — the accuracy
of this mapping is the point of the skill.

## Standardized Metric Taxonomy

The canonical metric types and their known source labels live in the master
workbook's **Metric Type Aliases** tab (Canonical Metric Type · Definition ·
Known Source Labels) — that tab is the single source of truth. Read it live at
the start of the run, the same way you read the Indication Aliases tab. The
current 7 types are: Total Prevalence, Diagnosed Prevalence, Treated Prevalence,
Addressable/Eligible Population, Incidence, Treatment Utilization, At-Risk
Population.

Classification notes carried over from prior decisions:
- "Under Rheumatologist care" → Addressable/Eligible Population (care-setting
  filter on the diagnosed population, not a treatment metric).
- ECOG 0-1 sub-population counts → Addressable/Eligible Population
  (performance-status-defined sub-population).
- Incidence is a flow, not a stock — never compare it to prevalence.
- Treatment Utilization line buckets (1L/2L/3L) can double-count one patient.
- At-Risk Populations are demographic denominators, not disease populations.

### New Metric Type (the taxonomy is extensible, not frozen)

The 7 types above are the *current* taxonomy, not a permanent ceiling. The point
of this skill is fidelity to the source — so if a new document reports a
population concept that does not honestly fit any existing type, treat it like a
missing alias:

1. **Fits an existing type** (possibly after conservative interpretation) → use
   it; flag the judgment call in the Data Quality Note if non-obvious.
2. **Plausibly new but ambiguous** → **stop and ask.** Show the source label,
   the closest existing type(s), and why it might not fit. Let the user decide
   between mapping it or creating a new type.
3. **Clearly a new concept** (no existing type is defensible) → **propose a new
   type and ask before using it.** Give a short proposed name, a one-line
   definition, and example source labels. Only after the user approves do you
   (a) use it in the granular CSV and (b) record it in the review note under a
   dedicated **"New metric type approved"** heading so it can be propagated.

When a new type is approved, it is added in exactly **one** place: a new data row
on the **Metric Type Aliases** tab (Canonical Metric Type · Definition · Known
Source Labels). Both the extractor and `pharma-epi-qc` read that tab at runtime,
so the new type flows everywhere automatically — there is no code list to keep in
sync. Never silently invent a type — ask, then add the row.

## Edge Cases

- **No epi data:** write `Epi data present: No`, explain what the document does
  contain, complete the Limitations section, and emit no Granular Data records
  (Sheet1 may still get a summary row noting no granular data).
- **Chart-only values:** extract if data labels are visible. If a value is only
  readable off an axis, record it with a Data Quality Note
  `"chart-only — requires manual read"`.
- **Sparse coverage:** list only indications with actual numbers; note in
  Limitations that TA coverage is broader than epi-data coverage.
- **Mixed metric types under one label:** use the footnote definition; flag the
  discrepancy in the Data Quality Note.
- **Projections vs. actuals:** always flag explicitly in the Projection /
  Methodology Note column.
- **Source arithmetic errors:** if a stated Total is inconsistent with the sum of
  geographies, keep the source's figures as-is and flag in Data Quality Notes
  (e.g. `"Total < sum of geographies — likely source formula error; use geo
  figures"`). Do not silently correct the source.

## Quality Check

- Did you list every indication with a number, not just the prominent ones?
- Are regional figures in the correct US/EU5/China/Japan columns (not merged),
  with empty cells where a geography isn't reported and integers only (no commas)?
- Are all geographies explicitly named (not assumed)?
- Is each row's Data Year stated, or did you assume it matches publication date?
- Did every uncertain row get a `flag:uncertain` token (and every known-wrong
  Total a `flag:red` token) in its Data Quality Note so the exporter paints it?
- Did you ask about every uncertain or missing alias rather than guessing, and
  emit an `*_aliases.csv` for every approved new term for the exporter to append?
- Does the granular CSV header match Granular Data A–P exactly, and the Sheet1
  CSV header match the Sheet1 tab's 8 fields (cols B–I, no companion-doc column)?
- Are limitations specific to this document, not generic boilerplate?
- If no epi data was found, did you say so clearly and explain why?
