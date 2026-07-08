# Source Adapter — GSK Epidemiology Report (annual / quarterly .xlsx)

**Applies to:** GSK's dedicated Epidemiology Report workbooks (FY2023, FY2024,
FY2025, Q1 2026 all share this template). Format: structured Excel, one patient-
population data point per row. This is the cleanest source ingested so far and
the recommended recurring anchor.

**Select this adapter when:** the user says the report is from GSK *and* it is the
dedicated epidemiology data workbook (not an earnings slide deck).

## Where the data lives

- **Overview tab** holds the data. One row per data point.
- Column layout (verified across FY2023-FY2025 + Q1 2026):
  - **B — Disease Area** (therapeutic area). **MERGED / forward-fill**: a value
    appears once and applies to the rows beneath until the next value.
  - **C — Indication**. Also **MERGED / forward-fill**.
  - **D — population / metric label** (the exact source wording, e.g.
    "Diagnosed prevalent patients", "Patients with 2 or more exacerbations per
    year", "1L drug-treated patients").
  - **E–I — US, EU5, China, Japan, TOTAL** (numeric).
  - **J — footnote / source reference**.

## Step-by-step interpretation method

1. **Read the Overview tab only.** Ignore other tabs (definitions/footnotes are
   reference, not data rows).
2. **Forward-fill** merged Disease Area (B) and Indication (C) down every data
   row so each row carries its own indication + TA.
3. **Map numerics to columns** E→US, F→EU5, G→China, H→Japan, I→Total of the
   Granular Data tab. A `"-"` (or blank) means *not reported* — leave the cell
   empty, never zero.
4. **Data Year = the report's fiscal year** (FY2023 report → Data Year 2023).
   GSK figures are point-in-time actuals for that year (the Q1 2026 report
   projects forward — check the report's own basis statement).
5. **Classify each metric label** to the 7-type taxonomy using this priority:
   (a) reuse the existing GSK *Original-Metric-Label → Metric-Type* mappings
   already in the live Granular Data sheet (most labels recur verbatim across
   years); (b) fall back to the Metric Type Aliases tab + heuristics for new
   labels. Vaccine **age-band** populations (e.g. "50+ population", "Infant
   cohort (0-2)") → **At-Risk Population**.
6. **Resolve indications** against the Indication Aliases tab (the extractor's
   standard alias-matching rules). GSK-specific override notes:
   - "SEA" / Severe Eosinophilic Asthma → fold into **Severe Asthma**.
   - Variant/typo/combined labels → use the explicit override map built from
     prior GSK ingests; new canonical seen so far: "Renal Anaemia (CKD)" (CVRM).
7. **Flag, don't fix:**
   - **Total ≠ sum of geographies** (material, >0.5%) → **red** fill on Total +
     DQ note. (GSK has several: HBV, Colon Cancer, CRSwNP "Total = US only".)
   - **Metric type inferred** from a clinical sub-population label (severity /
     biomarker / stage cut, not an explicit metric word) → **orange** on the
     metric-type cell + DQ note "verify".
   - Sub-0.5% Total-vs-sum gaps are **source rounding/float noise — do NOT flag.**

## Known data quirks (must normalize)

- **Thousands apostrophes**: `599'878'240` → strip the `'` before parsing.
- **Non-breaking / zero-width spaces**: `\u00a0`, `\u200b` appear inside labels
  and numbers — strip them.
- **Non-breaking hyphen** `U+2011` (e.g. in "MASH") breaks exact alias matching —
  normalize all hyphen variants to a plain `-` before matching.
- **China cells are often floats** (e.g. `1402766.892812411`) — round to integer
  on write (H–L are integer `#,##0`).
- `"-"` = not reported (empty cell), **not** zero.

## Yield / notes from prior runs

- FY2023 = 97 rows, FY2024 = 88, FY2025 = 93, Q1 2026 = 93. Extract ALL points
  (user preference), Data Year = report year, so the same indication recurs
  across years by design (longitudinal tracking, not duplication).
- 14 Total≠sum rows and ~10 inferred-metric rows per the full set — expected;
  flag per above.
- The user adds their OWN Sheet1 summary rows between turns — always re-read the
  last populated row live before appending; never assume row numbers.
