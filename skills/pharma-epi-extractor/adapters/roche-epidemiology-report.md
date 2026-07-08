# Source Adapter — Roche Epidemiology Master (annual PDF)

**Applies to:** Roche's "Epidemiology Master" annual reference PDFs (2023, 2024,
2025 ingested; same template). A dedicated, structured epi report — closer to the
GSK workbook than to a slide deck — but **asset/line-of-therapy-centric** and far
more granular. ~8–9 pages, one patient-population number per line.

**Select this adapter when:** the user says the report is from Roche *and* it is
the dedicated "Epidemiology Master" PDF (not a Pharma Day deck or earnings slides).

## Where the data lives

- Plain pages, no real table grid — text positioned in three numeric columns.
- Structure per block: **TA section header → indication block header → Roche
  drug(s) line (italic) → metric rows**. Indentation/font distinguish them
  visually, not reliably in text.
- **Columns are US / EU5 / China only — there is NO Japan column and NO Total
  column.** (Some indications report only US/EU5; China is frequently `NA`.)
- Metric rows are sliced by **line of therapy** (1L/2L/3L), **treatment status**
  ("treatment eligible" vs "drug-treated" vs "treated"), **stage**
  (neoadjuvant/adjuvant/early/locally-advanced), **biomarker** (PD-L1 high,
  PIK3CA+, KRAS G12C, t(11;14)), **age band**, and **subtype**.

## ⚠️ Critical extraction lesson — column x-positions shift by year

`pypdf` text extraction **fuses adjacent columns** into one run of digits
(e.g. `6,130,39220,626,465`). Use **`pdfplumber` with word positions instead.**

But the column x-coordinates are **not stable across years**, so a hardcoded
boundary will silently corrupt a whole year:

| Year | US center | EU5 center | China center |
|---|---|---|---|
| 2023 | ~325 | ~395 | ~471 |
| 2024 | ~363 | ~441 | ~517 |
| 2025 | ~351 | ~423 | ~502 |

A 2025-calibrated boundary (`US ≈ 340–405`) pushed the **2023 US column into the
label zone and dropped it**, shifting every 2023 value one column left (caught
only by the QC value-plausibility scan). **Fix / required method:**

1. For each page, read the x-centers of the `US`, `EU5`, `China` **header
   tokens**. Carry the last-seen centers forward to continuation pages.
2. Assign each numeric token to the **nearest** of those three header centers.
3. Treat a token as a **label** only if its center is well left of the US header
   (`center < US_center − 50`).
4. Group tokens into lines by `round(top / 3)`; join label tokens as the row
   label; place numbers per step 2.

Reference implementation: `/tmp/roche_final2.py` (extractor) and the
`roche_final2.py` aggregation block.

## Step-by-step interpretation method

1. **Extract** with the per-page nearest-header column logic above.
2. **Track context while walking lines:** a label-only line that matches a known
   indication name sets the current indication+TA; any other label-only line is
   stored as the current **sub-header** (needed for asthma/ophthalmology); drug
   lines are ignored.
3. **Map indication → canonical + TA** via the curated substring map (roll-ups
   below). Two blocks hold multiple indications and must be split at the row
   level: **IBD** → Ulcerative Colitis / Crohn's Disease; **"Obesity and
   Diabetes"** → Obesity / Type 1 Diabetes / Type 2 Diabetes.
4. **Aggregate per the user's rule** (confirmed 2026-06-25): for each
   `(year, canonical, metric type)`, **sum the non-subset line/stage rows** into a
   single figure; **never add rows that are explicit subsets** of another
   (PD-L1 high, PIK3CA+, endocrine sensitive/resistant, age/Type partitions when a
   total is also stated, ophthalmology New/Existing partitions). For each
   aggregated row, **highlight only the Total cell orange** (not the individual
   geography cells), and list the summed components in the Data Quality Note.
   Highlight a geography cell orange only if it is itself uncertain (e.g. a range
   midpoint) or especially suspect.
5. **Compute Total = sum of reported US/EU5/China** (leave a region cell blank if
   `NA`; Japan column always blank for Roche). **Leave the Projection /
   Methodology column blank** — do not write "US/EU5/China only" or "Total = sum"
   boilerplate; that is already obvious from the cells (user preference,
   2026-06-25).
6. **Resolve aliases** against the Indication Aliases tab (standard rules).

## Roll-ups & canonical mappings (confirmed 2026-06-25)

- **Breast Cancer** absorbs HER2+, HR+/HER2-, HER2+HR+, TNBC.
- **NSCLC** absorbs the molecular subtypes ALK+, ROS1+, KRAS G12C.
- **SMA** TA = Rare Disease, **IgAN** TA = Rare Disease — Renal,
  **CSU** absorbs "Chronic Idiopathic Urticaria (CIU)" — use each canonical's
  Aliases-tab TA, not Roche's section heading.
- 26 indications were net-new canonicals (added 2026-06-25): see the Aliases tab,
  incl. new TA groups **Ophthalmology** (nAMD, DME, RVO, DR, UME, TED) and
  **Immunology — Gastroenterology** (Ulcerative Colitis, Crohn's Disease).

## Metric classification specifics

- `(treatment) eligible` / `uncontrolled` → **Addressable/Eligible Population**.
- `incidence` (without "prevalence") → **Incidence**.
- `drug-treated` / `(treated)` / `1L–3L treated` / `R/R` / `induction` /
  `maintenance` / `anti-VEGF treated` → **Treatment Utilization**.
- `treated prevalence` / `drug-treated prevalence` → **Treated Prevalence**.
- `diagnosed …` → **Diagnosed Prevalence**; bare `prevalence`/`population`/COPD
  severity bands / `idiopathic` / obesity / diabetes → **Total Prevalence**.
- **Asthma:** the report lists three *overlapping* definitions (moderate-severe,
  uncontrolled, allergic). Use **"Uncontrolled" only** (Xolair-eligible) →
  Addressable/Eligible; summing all three would double-count.
- **Ophthalmology:** keep the prevalence tiers (top population → Total Prevalence,
  Diagnosed population → Diagnosed Prevalence, Anti-VEGF treated → Treated
  Prevalence); skip the New/Existing/Incidence sub-rows. The report **restructured
  this layout across years** (2023 "New/Existing" → 2025 per-tier
  "Incidence/Prevalence (existing cases)"), so use the sub-header to assign the
  tier, not just the row label.

## Known data quirks (normalize)

- Apostrophe thousands (`16'473`), `\u00a0` / `\u200b` spaces, float China cells.
- Source typos to absorb via normalized/fuzzy alias matching: "Flollicular",
  "Hodkin's", "Lympocytic", "Diagonsed", "Chrinic idiopathic urticarial",
  "Immunoglobun A Nephropahty", "Ealy stage".
- Ranges (e.g. SCD 2023 "55–120k") → midpoint, flag **orange** + note.
- `NA` / `-` = not reported (blank cell), never zero.

## Year-over-year inconsistencies to expect (record as-reported + flag)

- Indications added/dropped each year (SCCHN, ROS1+, ESCC, SCD, COPD drop;
  MDS/MCL/Alzheimer's/Parkinson's/TED/IBD/CVRM added later).
- Material definitional jumps in the same metric (Asthma mod-severe adults
  ~5× drop 2023→2024; DME population; Diabetic Retinopathy diagnosed ~3× rise;
  MM 2023 diagnosed+t(11;14)+2L vs 2025 R/R only). Keep each year's figure as
  reported and note the shift — do not reconcile across years.

## Yield (ingested 2026-06-25)

169 aggregated granular rows across the three years (52 / 60 / 57). All aggregated
rows orange-flagged; Roche rows passed clean-slate QC (0 orphan / TA / metric-type
issues; Total = sum by construction). Output appended to the master at Granular
rows 387–555.
