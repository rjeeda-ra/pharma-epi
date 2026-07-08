# Source Adapter — Roche "Target Patient Populations" chart deck (stacked-bar slides)

**Container:** PDF slide deck (960×540 landscape). **Representation:** chart /
graphic — the numbers live *inside stacked bars*, read from printed data labels.

**Applies to:** Roche "*Appendix: Potential target patient populations*" Pharma-Day
decks. Worked examples ingested: **2021** (52 pp) and **2022** (40 pp) — same
template family. ~34 chart pages, one indication per page, plus TA divider /
title / closing pages. Figures are Roche-internal **actuals** for the deck year.

**Select this adapter when:** the source is a Roche slide deck whose chart pages
show **stacked vertical bars with a per-page color legend** — *not* the Roche
"Epidemiology Master" structured-text PDF (that is the positioned-text guide,
`roche-epidemiology-report.md`). Same company, different representation → route on
the page, not the name.

> **Scope note.** Roche has since changed this format, so treat this guide as a
> *how-to-read-a-stacked-bar-deck* method (colors → data labels → geographies),
> anchored on 2021/2022, rather than a Roche-forever spec. The reusable part is
> the **chart-reading style**; the per-year specifics (palette, legend encoding)
> must be re-derived every run — see the critical lesson below.

## ⚠️ Critical lesson — the color palette AND legend encoding change by year

This is the chart analogue of the positioned-text guide's "column x-positions
shift by year." **Never hardcode the swatch RGBs or assume the legend is drawn
the same way.** Observed:

| Year | EU5 fill | US fill | China fill | Legend encoding |
|---|---|---|---|---|
| 2022 | `(0.008,0.137,0.4)` | `(0.043,0.255,0.804)` | `(0.078,0.51,0.98)` | **vector** 7×7 swatch rects + text (pdfplumber reads it) |
| 2021 | `(0.0,0.396,0.671)` | `(0.0,0.475,0.8)` | `(0.678,0.769,0.918)` | **rasterized** — legend is baked into the chart image; pdfplumber sees no swatch/text (read it with the Visual read) |

The **only stable pattern** is the tonal ramp: **darkest = EU5, mid = US, lightest
= China**, and stacking order matches (EU5 bottom → China top). So each run,
establish the color→geography map with this **precedence**:

1. **Vector legend, if present (best when it's text).** Look for small colored
   **7×7 `rect` swatches**; for each, the geography word (`EU`/`EU5`, `US`,
   `China`, `Japan`) sits immediately to its right (`geo_x0 ≈ swatch_x0 + 11`,
   same `top`). Build the **swatch-color → geography** map for *that page*
   (this is the 2022 case).
2. **Rasterized legend → Visual read (authoritative, not a guess).** When
   pdfplumber returns no swatch/text legend, the legend is almost always
   **baked into the chart image** rather than absent (this is the 2021 case).
   **Do not jump straight to the tonal ramp.** Render the page and read the
   legend with your own vision (see INDEX.md "Visual read"):
   `pdf.pages[i].to_image(resolution=170).save("/tmp/pg.png")` → `Read` the PNG →
   fix the color→geography mapping from the picture, *then* return to pdfplumber
   for the precise segment colors and numeric labels. Lock this once per template
   (one representative page), not every page.
3. **Tonal ramp = last-resort fallback only.** If even the visual read is
   inconclusive (no legend anywhere), fall back to darkest→lightest =
   EU5→US→China and **cross-check with magnitude** (China usually smallest or
   absent; US often largest) before trusting it.
4. Match each bar segment's `non_stroking_color` to the legend map to assign its
   geography. Confirm color equality with a small tolerance (±0.02), not `==`.

## Where the data lives

- **Bars are `rect` objects** (good — pdfplumber reads their fill + geometry).
  Group all rects on a page by `non_stroking_color`; the 2–3 stacked-segment
  colors are the geographies, everything else (page frame, tables) is chrome.
- **Every value is a printed data label** on/next to its segment — values in
  **thousands** (×1000 into the CSV). Per the standing rule, **printed labels are
  authoritative; bar height × axis scale is only a cross-check / last resort**,
  never the source of a number.
- Bars cluster into **categories along x** (each category = a line/stage/subtype).
  Group segments into a stack by shared bar-center x.
- **Columns present are EU5 / US / China only — no Japan** (blank, not zero).
  China is frequently absent (blank) where the deck shows NA.
- `~N` labels floating **above a stack** = the **stack total** (e.g. 2022 eBC
  `~151`, `~76`). Use them **only to cross-check** the sum of segments; do not emit
  them as a separate row.

## ⚠️ Data labels are split into single characters

pdfplumber returns each digit as its own `char` (e.g. "504" = chars at x≈173/178/183
sharing one baseline; 2022 eBC "467" at x≈295/300/305). **Reconstruct** before
reading:

1. Take `page.chars` that are digits or `.`; drop the rotated y-axis label chars
   (constant tiny x, marching top — the vertical "no. of patients" / axis).
2. Group by baseline (`round(top)` within ±2).
3. Within a baseline, sort by `x0` and **merge adjacent chars whose x-gap < ~4px**
   into one number; a larger gap starts a new label.
4. Associate each reconstructed number with the nearest segment of its bar-cluster
   (same x-center), then to a geography via that segment's color.

## Step-by-step read method

1. **Classify the page:** title/divider/closing → skip. Chart page → proceed.
2. **Build the page legend** (swatch→geography) per the critical lesson.
3. **Collect bars:** group rects by fill color; cluster by x-center into stacks
   (one stack per category). Record each segment's (color, height, category-x).
4. **Reconstruct data labels** (split-digit merge) and attach to segments.
5. **Assign geography** by segment color via the legend map; put the label value
   in the matching US/EU5/China column (×1000). Japan blank; China blank if absent.
6. **Cross-check** with the `~N` stack total and with height×scale; if a label
   can't be read confidently, record the height-derived value and note it.
   When a parsed value looks wrong (a split-digit misread, a suspicious
   magnitude, a geography that seems swapped, a Total that won't reconcile),
   **render that page and confirm against the picture** (INDEX.md "Visual read")
   before trusting or flagging it — this distinguishes a *parse error* (fix it)
   from a *genuine source oddity* (carry it, flag it).
7. **Aggregate per the Roche convention** (same as the positioned-text guide):
   one granular row per (indication × metric); value = **sum of mutually-exclusive
   line/stage components**; **never add explicit subsets** (biomarker/age/stage
   partitions). List summed components in the Original Metric Label + DQ note.
8. **Every chart-read row carries `flag:uncertain`** (chart-only read) — this is
   expected for the whole deck, not a per-row anomaly. Resolve aliases and metric
   types via the live tabs (standard rules); then write outputs.

## Known quirks to normalize

- **Split-digit labels** (above) — the #1 source of misreads. A cramped small
  label can drop/duplicate a digit; cross-check the `~N` total (e.g. 2022 HER2+ US
  had to be corrected 39→**38** off small text).
- **`~N` = total, not a segment** — never emit as its own value.
- **Japan absent deck-wide** (blank column). **China often NA** (blank ≠ zero).
- **Category label sometimes not printed** (single-bar prevalence pages) — record
  conservatively and flag.
- **Line-bucket Treatment Utilization rows (1L/2L/3L) can double-count** a patient
  — flag uncertain accordingly.
- **Multi-series pages beyond geography** (e.g. 2022 p35 Asthma = 4 series: EU
  adults / EU adolescents / US adults / US adolescents, no China/Japan). Verify the
  color→series map against the legend + a height cross-check, then combine per the
  user's rule (adult + adolescent per geography). Use only the **Uncontrolled**
  definition (Xolair-eligible → Addressable/Eligible); omit overlapping
  moderate&severe / allergic definitions to avoid double-count.
- **Absolute-number Rx-opportunity tables** on a chart page (e.g. 2022 eBC HER2+
  1L–4L table in absolute patients, mixed with thousands charts) — **do not fold
  into the thousands rows**; defer to a manual pass to avoid unit-mixing.

## Metric classification & roll-ups

Follow the same taxonomy and canonical mappings as `roche-epidemiology-report.md`
(Breast Cancer absorbs HER2+/HR+/TNBC; NSCLC absorbs molecular subtypes; CSU
absorbs CIU; ophthalmology prevalence tiers; asthma Uncontrolled-only). Assign
metric type from the category/sub-header label, not the bar color.

## Yield / validation notes (2022, ingested 2026-07-01)

51 granular rows (values ×1000, Total = sum of present US/EU5/China, every row
`flag:uncertain`). Cross-checks passed: 2022 eBC `~76 = 21+23+32`,
`~151 = 36+14+101`; HER2+ US corrected 39→38. New canonical approved: **IPF →
Rare Disease**; iNHL page mapped to **Follicular Lymphoma (FL)** only. Asthma p35
combined: **EU5 2,059k, US 3,591k** (adult+adolescent, Uncontrolled def). Exported
into the master at Granular rows 556–606.

## Yield / validation notes (2021, ingested 2026-07-01)

52-pp deck, 38 chart pages → **84 granular rows** (values ×1000, Total = sum of
present US/EU5/China, every row `flag:uncertain` — whole-deck chart read). TA
spread: Oncology 46, Ophthalmology 11, Rare Disease 10, **Rheumatology 8 (new TA
this run)**, Immunology — Gastroenterology 4, Neurology 3, Immunology — Systemic
Autoimmunity 2. Legend was **rasterized** (no vector swatch/text) → the
darkest→lightest = EU5→US→China ramp was **visually confirmed** by rendering and
reading pages 6, 9, 15, 16, 22, 29 (INDEX.md "Visual read"). Split-digit fix via
visual verify: **HCC 1L-treated China 13.2 → 128.4k**. A **reviewer visual pass**
(re-rendered p17/p29/p49) is a clean worked example of the visual read separating
*parse errors* from *genuine oddities*:
- **ESCC (p17) — parse error, fixed:** China was misread; correct is *Esophageal
  incidence* EU5 28 / US 17 / **China 347**, and *ESCC subset* **China 309** (the
  tiny EU5+US bottom ~16k is overlapping/illegible → left blank, row flagged).
- **GCA (p49) — false discrepancy, cleared:** two *separate* bars, not one — Diagnosed
  EU5 86+US 237 = 323k; Treated EU5 79+US 225 = ~303k. No cross-check gap.
- **mCRPC — confirmed genuine:** EU5 239.1k ≫ US 49.6k is real as drawn (caveat removed).
- **RVO (p29) — confirmed genuine oddity, carried:** US column alone is inconsistent
  (US population 258k < US diagnosed 693k); EU5 funnel and the totals are monotonic.
8 new canonicals approved (Melanoma, Bladder Cancer (Urothelial), RCC, Prostate
Cancer, Geographic Atrophy (GA), sJIA, pJIA, GCA). p4 HER2+ mBC absolute-number
Rx-opportunity table deferred (unit mixing).
