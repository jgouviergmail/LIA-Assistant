# ADR-274 — The craft belongs to the renderer, the meaning to the model

**Status:** Accepted — 2026-09-08
**Amends:** ADR-226 (document generation agent), ADR-184 (what a system
enforces, it publishes), ADR-085 (boot-time completeness)

---

## Context

Owner observation, 2026-09-08: *"document generation works, but the layouts are
basic, unworked and unattractive — most visibly on PowerPoint, but on every
format"*. The prompt was suspected. It was not the cause: the prompt already
asked for more than the system could render.

Two ceilings, both in code, both **measured**:

| Ceiling | Measurement |
|---|---|
| The vocabulary | `Slide` was `title + bullets + notes`; `SectionBlock.kind` had four values. A twelve-slide deck was twelve times the same layout, whatever the prompt asked. |
| The renderer | `pptx.Presentation()` = the stock **4:3** template, **2 of its 11 layouts** used; `docx.Document()` = **4 of 164** named styles; the PDF went through PyMuPDF's Story with **no stylesheet at all**; xlsx got bold headers and column widths. |

Six more measurements shaped the design:

- **A dense slide overflowed by 1 087 pt** (1 444 pt of text in a 356 pt
  frame). `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` changed nothing — PowerPoint
  computes no autofit on open — and python-pptx's own `fit_text` chose 21 pt
  where PowerPoint still measured 364 pt of overflow.
- **Excel REFUSES to open a workbook** whose Table has a duplicate or empty
  header, or a name with a space; openpyxl writes all three happily.
- **Word's `TOC Heading` is based on `Heading 1`**: left alone, "Contents" is
  counted as chapter 1 and appears in the contents it introduces.
- **MuPDF repaints a phantom header rectangle** at the top of every
  continuation page when a `th` carries a background under `border-collapse`.
- **PyMuPDF bundles its fonts** (Nimbus Sans, Droid Sans Fallback for CJK), on
  Windows and inside the Linux container alike — no system font is needed.
- **`SectionedContent` has been outside OpenAI's strict mode since ADR-226**
  (nesting depth 6 > 5, because a table inside a repeated block costs two
  levels). Nobody had measured it; docx/pdf/md/txt have run on
  `function_calling` ever since, without incident.

## Decision

1. **The craft belongs to the renderer; the meaning belongs to the model.**
   The model says what a thing IS — an ordered sequence, a quote, a warning, a
   section opener, a comparison, data — and the renderer decides how it is
   drawn. No layout catalogue, no brand identity, no vendored `.dotx`/`.potx`.
2. **Native mechanisms, never imitation.** Word: named styles, `PAGE`/
   `NUMPAGES` fields, a numbering definition, header and footer parts.
   PowerPoint: the template's own layouts and placeholders, the slide-number
   field, built-in table styles. Excel: typed cells, number formats, a named
   Table, freeze panes, autofilter. PDF: a stylesheet, outline bookmarks,
   links, exact page numbers.
3. **Nothing overflows, by construction.** `fit.py` measures text before it is
   placed, CALIBRATED against PowerPoint 16 on 54 combinations: any average
   glyph width in **[0.426, 0.493] em counts every line exactly** (0.46 is
   taken near the middle, because the calibration string is narrower than
   prose with capitals), and `lines × size × 1.2 + paragraphs × size × 0.2`
   times **1.05** turns 18 under-predictions into **none**. What does not fit
   is shrunk to 14 pt, then SPLIT into "Title (2/3)" slides; a bullet too long
   for a slide is cut at sentence boundaries — never clipped.
   **A full-width glyph is one em BY DEFINITION**, not the width calibrated on
   Latin prose — and every calibration measurement was Latin. Counting an
   ideograph at 0.46 em measured a dense Chinese slide at 238 pt where it takes
   442 pt in a 356 pt frame, and the overflow ORACLE agreed with the renderer
   because both read this module. PowerPoint settles it: the same deck reports
   **2 overflows, one of 124.1 pt, under the Latin width and 0 under the
   corrected one**. The rule is a strict generalisation — a Latin string still
   measures `len × 0.46` — so the 54 fixtures hold unchanged, and ONE notion of
   width now serves the three places that measure one: the line count, the pptx
   table's column weights and the xlsx column widths. All three counted code
   points, so a CJK column was starved by half, its cells wrapped, and the rows
   grew past the height the renderer had reserved — where the oracle cannot
   see them, a table being a graphic frame and not a text frame.
4. **Every incoherence is repaired, none is refused** (ADR-184). Levels are
   clamped, empty blocks dropped, markdown that leaked into a paragraph
   converted to the block it is, model-written heading numbers stripped when
   the renderer numbers, ragged rows WIDENED (truncating would lose what the
   model wrote), headers made unique, and **the characters XML forbids
   removed** — python-docx raises "All strings must be XML compatible" and
   openpyxl raises `IllegalCharacterError`, so a model echoing a form feed out
   of an extracted PDF killed the render AFTER the call was paid for. A list
   the model put in `text` instead of `items` is READ as the list it is: the
   fallback used to flatten it into one line of prose carrying a stray dash,
   which also made normalization non-idempotent — the second pass recognised
   the markdown the first had destroyed. The `level` bound is REMOVED from the
   schema: a bound fails the whole document — three paid times — over one
   heading (the ADR-269 lesson). `min_length=1` stays: a document with nothing
   has nothing to render.
5. **ONE predicate decides the long-document apparatus.**
   `document_is_numbered` switches the table of contents, the heading
   numbering and the page break before each part TOGETHER. A caller that
   already shapes its document pins `structure="plain"`: **meeting minutes do**
   (owner decision), so they gain the running head, the pagination and the
   table craft and keep their shape.
6. **Word's contents is pre-rendered without page numbers** (`\n` switch, live
   links): the field is empty until Word recomputes it, so a document opened
   and printed immediately would otherwise show a blank contents page. F9
   regenerates it identically. **The PDF's contents carries EXACT numbers**,
   because we paginate it ourselves: the body is laid out once — it never
   contains the contents, so nothing it does can move — and the front matter is
   laid out again with the numbers that follow, then the two are concatenated,
   which also gives the contents its own page.
7. **What the renderer enforces, the prompt publishes** (ADR-184): slide
   density, bullet length, the contents threshold and a length budget derived
   from the slot's `max_tokens` travel as placeholders read from settings,
   each with the consequence of its overrun stated. **The length budget is
   PER FAMILY**, because the families do not have the same economics: measured
   with `o200k_base` on realistic large documents, prose and slides converge to
   **0.69 words per output token** and a workbook to **0.25** — short cells
   make the JSON structure dominate. One factor for the three published a
   number **2.2× too generous for a spreadsheet**, so a model obeying the
   budget it was given would still be cut at it, which is ADR-184's trap
   turned on its author.
8. **A4 by default** (`DOCUMENT_GENERATION_PAGE_SIZE`); slides are **16:9
   LANDSCAPE**, obtained by scaling the default template's OWNED transforms —
   writing an inherited position freezes a placeholder at height 0.
9. **Neutral by design**: ink on paper, greyscale only, one band, one rule.
   `typography.py` is the single place a look is decided, so a future theme is
   a parametrisation of one module rather than a sweep through five renderers.
10. **The vocabulary costs the slide family its strict mode**, and that is
    accepted: a table inside a repeated block costs two nesting levels, so
    `SlideContent` joins `SectionedContent` at depth 6 while `TabularContent`
    stays strict. The alternative — hoisting tables to the document root and
    referencing them by index — buys strict mode by handing the model an index
    it can get wrong, which is the trade ADR-184 refuses. The verdict is
    measured and PINNED per family, so it cannot move in silence.

## Consequences

- **Measured after implementation** (`task documents:corpus:measure`, Office 16
  over the 13-document corpus): **0 slide overflows on 69 slides**, all
  960 × 540 pt; Word computes its fields (`Page 1 / 10`, and
  `第 1 页，共 7 页` on the Chinese document), the contents exists on the long
  documents and not on the short ones, headings are numbered `[1] [2] [3]`;
  Excel opens every workbook without repair, with its Table and frozen header.
- **Cost** (tiktoken, o200k_base): the prompt goes from **855 to 1 234 tokens**
  and the schema from 193–431 to 259–597. The manifest's published estimate is
  raised from 2 000 to 2 500 input tokens rather than left to drift.
- Meeting minutes gain the craft and keep their shape; every other consumer of
  `render_document` is unchanged (the context is optional).
- **Five registries keyed by the vocabulary now refuse a partial map at import**
  (ADR-085): the docx, markdown, plain-text and slide registries are total, the
  PDF one is deliberately partial and states its complement. The vocabularies
  are READ from the schema (`BLOCK_KINDS`, `SLIDE_KINDS`), never typed twice.
- No new spend site, no new LLM call, no frontend change: the cards are native
  links, and `LLM_SPEND_ROADS` is untouched.
- **The PDF stamps carry their own font.** The Story embeds a CJK fallback for
  the BODY; the running head and the footer are drawn separately with
  Helvetica, which has no ideograph — so a Chinese report was stamped
  `······` and `· 1 ··· 1 ·` on every page while its body was perfect. The
  stamp font is now chosen by asking Helvetica whether it has the glyphs
  (`stamp_font`), so a Latin document keeps the file it had and the CJK face is
  reused rather than added: measured, the Chinese PDF goes from 3 917 KB to
  3 900 KB — Helvetica leaves it — and the 500-block report still renders in
  0.22 s. Writing the stamps through a `TextWriter` also revealed that it
  measures y from the BOTTOM where `insert_text` measures it from the top: the
  first version silently swapped the head and the footer, and the band oracle
  written for the CJK defect is what caught it.
- **A Chinese PDF weighs about 3.9 MB** whatever we do — the embedded CJK face
  dominates, and `subset_fonts()` does not shrink what the Story embedded.
  Stated rather than discovered on the attachment quota.
- **A wide PDF table is shrunk by a measured ladder**, found by looking at a
  rendered corpus document rather than by a test: MuPDF sizes columns from
  their content and honours neither `width: 100%` nor `table-layout: fixed`, so
  a 12-column table reached **714 pt on a 595 pt page**. The oracle reads the
  table's RULES, because the extracted TEXT stops at the last glyph and hides
  the overflow (544 vs 714 on the same table).
- **Stated limits.** The estimator is calibrated on Calibri metrics (Carlito is
  metric-compatible; other viewers substitute — the 14 pt floor and the 5 %
  margin cover the common case). Word's contents shows no page numbers until
  F9. Integers carry no thousands separator, because a year and a postal code
  are integers too. Beyond 16 columns a PDF table overflows whatever the size
  (20 columns overflow even at 5 pt) — `PDF_TABLE_MAX_FITTING_COLUMNS` says so.

## Alternatives rejected

1. **Improving the prompt alone**: it would write better sentences into the
   same grey box. The prompt was already asking for more than the renderer
   could produce.
2. **A vendored `.dotx`/`.potx` template**: that is an identity, opaque to
   review, and it drifts. The owner asked for the opposite.
3. **A layout catalogue chosen by the model**: it would hand the model a
   drawing decision it cannot judge, and freeze the renderer's freedom to
   improve.
4. **`python-pptx.fit_text`**: measured wrong by a factor of two.
5. **`updateFields` on open** for Word's contents: a dialog on every open.
6. **A new PDF dependency** (reportlab, weasyprint): ADR-226 already rejected
   one, and the Story engine plus a two-pass layout gives exact numbers.
