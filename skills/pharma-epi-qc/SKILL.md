---
name: pharma-epi-qc
description: >-
  Read-only standardization QC for the Epidemiology Master Sheet. Audits the
  Granular Data tab against the Indication Aliases tab (canonical indication
  names + therapeutic areas) and the Metric Type Aliases tab (the metric
  taxonomy, read live from the workbook), then emits a
  qc_report.md exceptions report. Use after data has been exported into the
  master workbook, on a periodic audit, or when the user says "QC the sheet",
  "check standardization", "audit indications/metrics", "are indications and
  metrics tracked consistently", or "find inconsistencies in the master sheet".
  This is the third skill in the pipeline (extractor -> exporter -> qc). It
  NEVER writes to the workbook; fixes are proposed and applied only after the
  user signs off.
---

# pharma-epi-qc

## What This Skill Produces

A single Markdown file, `qc_report.md`, listing every standardization exception
in the Epidemiology Master Sheet, grouped into three tiers and prefixed with a
pass/fail summary table. It changes **no cells** — it is a diagnostic. Any fix
is a separate, human-approved follow-up pass.

> **Pipeline reference:** `../pharma-epi-extractor/reference/pipeline.md` is the
> single source of truth for the definition of done, the flag legend, the full
> target schema, the Box constraint, and the investment-use/recordkeeping
> reminder. This SKILL covers only the QC step.

## Where It Fits

```
pharma-epi-extractor  ->  pharma-epi-exporter  ->  pharma-epi-qc
   (read source)          (write local .xlsx)      (audit the .xlsx)
```

Run QC after one or more exports have landed in the master workbook — it catches
drift that accumulates across sources and ingestion dates (e.g. an early source
using a now-retired therapeutic-area label). The extractor enforces per-row
standardization at write time; QC is the periodic whole-sheet backstop.

## Trigger Conditions

- "QC the sheet" / "run a quality check" / "audit the master sheet"
- "check that indications and metrics are tracked/standardized properly"
- "find inconsistencies" / "are the therapeutic areas consistent"
- After a batch export, before sharing or relying on the workbook

## Clean-slate / independent review (avoid grading your own homework)

QC is most trustworthy when the reviewer is not the same context that produced
the data. Two safeguards, in order of strength:

1. **The check is deterministic code, not judgment.** `qc.py` compares cell
   strings against the Aliases tab and the taxonomy set. It does not "remember"
   how the data was extracted and cannot rationalize a bad mapping — it simply
   reports mismatches. This is the primary safeguard and runs every time.
2. **Run the judgment layer in a fresh context.** For the interpretive parts
   (e.g. confirming the "inferred metric" rows, or deciding whether a near-dup
   canonical is truly distinct), dispatch a **subagent (Agent tool) with a clean
   context** whose only inputs are this skill, the workbook, and the
   `qc_report.md` — *not* the extraction/export chat. Ask it to independently
   verify the report's findings and look for anything missed. This gives a
   genuine second set of eyes within the tool.

Honest limit: a subagent is still Claude, not a human or a different model — it
reduces context-carryover bias but is not fully independent. For high-stakes
sign-off, a human reviewer remains the gold standard (and is required by the
investment-use rules anyway). Offer the subagent review by default on any
non-trivial QC run.

## How To Run

1. **Get a local copy of the master workbook.** Box is text-only in this
   environment, so QC runs on the same local `.xlsx` the exporter produces (or a
   freshly downloaded copy the user provides). Confirm you are auditing the
   latest version.
2. **Run the diagnostic:**
   ```
   python3 qc.py "<path to master>.xlsx" --out qc_report.md
   ```
   (Needs `openpyxl`: `pip install openpyxl` if missing.)
3. **Read `qc_report.md` and walk the user through it.** Summarize the headline
   findings; do not bury them.
4. **Propose fixes, get sign-off, then apply in a separate pass.** When applying
   approved fixes, re-stamp the output filename with the current date/time in the
   house format `Epidemiology Master Sheet (DD Month YYYY, H:MMam/pm).xlsx`
   (day no leading zero, full month, lowercase am/pm, no space), and re-run
   `qc.py` to confirm the exceptions cleared.

## What It Checks

**Tier 1 — Indication & Disease Area**
- Every `Indication (Standardized)` (col E) exactly matches a Canonical
  Indication Name in the Aliases tab (case/punctuation-insensitive). Flags
  orphans and rows left on an alias instead of the canonical.
- `Disease Area` (col C) equals the canonical's Therapeutic Area, and is
  consistent across every row for a given indication. (This is the most common
  failure — legacy/source-specific TA labels such as a slide-section name or an
  old TA spelling.)

**Tier 2 — Metric standardization**
- Every `Metric Type (Standardized)` (col G) is exactly one of the canonical
  types read from the Metric Type Aliases tab (no casing/spelling variants).
- The same `Original Metric Label` (col F) never maps to more than one
  standardized type across the sheet.
- Lists rows whose metric type was `inferred` (judgment calls needing a human
  eyeball).

**Tier 3 — Total vs sum-of-geographies**
- Flags rows where the stated Total differs materially (> 0.5%) from the sum of
  populated US/EU5/China/Japan cells — candidates for a red flag + DQ note.
- Separately lists sub-0.5% mismatches as rounding/float noise (left unflagged),
  so genuine errors are not drowned out.

## The Taxonomy & Source of Truth

- **Canonical indications + therapeutic areas:** the live **Indication Aliases**
  tab. If the workbook's TA naming evolves, update the Aliases tab first — it is
  the single source of truth this skill audits against.
- **Metric types:** the live **Metric Type Aliases** tab. `qc.py` reads col A of
  that tab at runtime to build the valid-type set, so the taxonomy is defined in
  exactly one place — there is no list hardcoded in the script to keep in sync.
  The taxonomy is **extensible, not frozen**: when the extractor proposes and the
  user approves a new type, add a row to that tab (Canonical Metric Type ·
  Definition · Known Source Labels) and QC picks it up automatically on the next
  run. The current 7 types: Total Prevalence, Diagnosed Prevalence, Treated
  Prevalence, Addressable/Eligible Population, Incidence, Treatment Utilization,
  At-Risk Population.

## Boundaries

- **Read-only.** Never edit the workbook from this skill. Fixes are a separate,
  approved step (and `qc.py` re-run afterward to confirm).
- Does not re-classify data or re-extract from sources — it only checks
  internal consistency against the Aliases tab and the taxonomy.
- The 0.5% rounding tolerance is tuned to GSK's float artifacts; adjust
  `ROUNDING_TOLERANCE` in `qc.py` if a future source needs it.
