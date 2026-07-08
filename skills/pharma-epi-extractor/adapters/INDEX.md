# Reading-Method Library — Index & Selector

This folder is the `pharma-epi-extractor`'s **document-reading library**: one
guide ("adapter") per source type, describing exactly how to pull epi numbers
out of that document. It is **bundled inside the skill** (this
`adapters/` folder) so it travels with the skill to any user, and it is
**lazy-loaded** — only `SKILL.md` auto-loads; a guide is `Read` only when its
source is selected, so the library can hold many guides without bloating the
skill.

- **Location:** `adapters/` inside the skill (reference guides by the relative
  path `adapters/<file>.md`).
- **This file** is the registry + selector — **read it first** each run.

## How the extractor picks a method (route by *representation*, not company)

The thing that determines the reading method is **how the numbers are
physically encoded on the page** — not which company published it (one company
can ship several formats; Roche ships both a positioned-text PDF and a
bar-chart deck). So selection is a two-part key:

**Step A — Container (picks the tool):**
- Spreadsheet (`.xlsx`/`.csv`) → openpyxl / cell reads
- PDF or slide deck → pdfplumber (text + positions + rects), **plus the visual
  read below whenever critical content is rasterized** (see "Visual read").
- *(future: `.pptx`, HTML, scanned image → OCR)*

**Step B — Representation (picks the parsing logic):**
1. **Structured cells** — a spreadsheet grid, or a true ruled table in a PDF →
   read cells/table directly.
2. **Positioned text** — PDF text laid out in columns by x-coordinate with no
   real grid → assign each token to a column by position (pdfplumber words).
3. **Chart / graphic** — values live inside bars/lines/pie → read data labels +
   map series via the color legend + use bar geometry only as a cross-check. If
   the legend is **rasterized** (part of the chart image), read it with the
   Visual read below, then take numbers from the vector labels.
4. **Narrative / slide** — numbers scattered in prose, callouts, or innovation
   slides → scan-and-harvest, mostly manual.

**Procedure:** determine (container, representation) → find the matching guide
in the Selector below → `Read` it and follow it in place of the generic Step 1–2
scan → continue the shared Steps 3–6. If nothing matches, use the generic scan;
if the source recurs, **author a new guide here** (see "Adding a guide").

## Visual read — the rasterized-content fallback (any PDF/deck)

pdfplumber only sees *vector* text and shapes. When the information you need is
**baked into an image** — a legend that is part of the chart picture, a scanned
page, a flattened table, data labels rendered as graphics — pdfplumber returns
nothing (or garbage) for it, and you must **read the page as a picture** with
your own vision:

```python
pdf.pages[i].to_image(resolution=170).save("/tmp/pg.png")   # then Read the PNG
```

Then `Read` that PNG and interpret it directly (multimodal). Two standing uses:

1. **Lock semantics you can't extract as text.** The clearest case is a
   **rasterized color legend** (swatch → geography/series): render once, read the
   legend visually to fix the mapping, *then* go back to pdfplumber for the
   precise numeric values. This is the authoritative way to establish a
   color→series map when the legend is a picture — better than guessing from a
   tonal ramp. (See the chart-deck guide's legend step.)
2. **Verify ambiguous or contradictory parses.** When a pdfplumber value looks
   wrong (a split-digit misread, a suspicious magnitude, a geography that seems
   swapped, a Total that won't reconcile), render that page and confirm against
   the picture before trusting or flagging it. A visual check distinguishes a
   *parse error* (fix it) from a *genuine source oddity* (carry it, flag it).

**Cost / discipline:** rendering + reading an image is slower and heavier than a
text read, so use it deliberately — to lock a legend once per template, and to
spot-check the handful of values that don't reconcile — not to read every page
by eye when the vector text is clean. Prefer printed/vector labels as the source
of numbers; use the visual read for semantics and verification.

## Selector

| Container | Representation | Source / report type | Guide file | Status |
|---|---|---|---|---|
| Spreadsheet (.xlsx) | Structured cells | **GSK epidemiology workbook** (FY/Q); one row per point | `adapters/gsk-epidemiology-report.md` | ✅ validated |
| PDF | Positioned text | **Roche "Epidemiology Master"** annual PDF (2023–25 template); 3 numeric columns US/EU5/China; asset/line-of-therapy rows | `adapters/roche-epidemiology-report.md` | ✅ validated |
| PDF (slide deck) | Chart / graphic | **Roche "Target Patient Populations" appendix**; stacked-bar data labels in thousands; ~34 chart pages | `adapters/roche-target-populations-chartdeck.md` | ✅ validated |

*(Guide files are named by source for human recognition; the two left columns
are the routing key. When you add a guide, tag it with its container +
representation at the top of the file.)*

## Disambiguation (when the source is ambiguous)

- **Same company, different representation.** Never route on the company name
  alone. Roche → check the page: three-column text/table = **positioned text**
  guide; stacked bar charts with a color legend = **chart** method.
- **.xlsx vs PDF** is the fastest first cut (Step A). A workbook is almost
  always the structured-cells path; a PDF still needs the Step B layout check.
- **Table vs positioned text inside a PDF:** ruling lines / a real grid →
  structured cells; columns held only by whitespace/position → positioned text.

## Adding a guide

When a source recurs and is worth standardizing, create
`adapters/<source>.md`, add a Selector row, and tag the file with its
(container, representation). Mirror an existing guide's structure and document:

1. **Applies to / Select when** — container + representation + trigger cues.
2. **Where the data lives** — page/tab structure, columns, what to ignore.
3. **Step-by-step read method** — the exact procedure + extraction gotchas +
   required tool.
4. **Known data quirks to normalize** — typos, encodings, ranges, NA handling.
5. **Source-specific mappings** — indication roll-ups, metric classification,
   aggregation rules.
6. **Yield / validation notes** — what a good run produced last time.

> **Future refactor (not yet built):** because guides now route by
> representation, the shared *how-to-read-a-stacked-bar-chart* /
> *how-to-read-positioned-columns* logic can be pulled out into reusable
> **method primitives**, leaving each per-source guide as just its color map,
> roll-ups, and quirks — making "style" the reusable part and "company" the thin
> part.
