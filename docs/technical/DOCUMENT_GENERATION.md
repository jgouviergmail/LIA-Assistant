# AI Document Generation (ADR-226, ADR-274)

> Downloadable documents (csv, xlsx, docx, pptx, pdf, md, txt) written by a
> dedicated LLM slot, rendered locally with the libraries already embedded for
> RAG extraction, stored as TTL attachments and delivered as cards below the
> assistant response. Architectural mirror of
> [IMAGE_GENERATION.md](./IMAGE_GENERATION.md).
>
> **The craft belongs to the renderer, the meaning to the model** (ADR-274):
> the model says what a thing IS; the renderer decides how it is drawn, using
> the native mechanisms of each format.

## Overview

`generate_document(instructions, doc_type, source_data?, filename?)` gives the
assistant its "produce a file" capability in both execution modes: as a plan
step in pipeline mode (chaining research → document via `$steps` templating on
`source_data`) and as a regular tool in ReAct mode.

### Features

- 7 output formats behind one tool, validated against a closed enum that is
  **published** to the planner (ADR-184 doctrine).
- Content produced by the `document_generation` LLM slot (admin-configurable;
  default `openai/gpt-4.1`) via structured output, with the schema selected per
  format family BEFORE the call: tabular (csv/xlsx), sectioned
  (docx/pdf/md/txt), slides (pptx).
- **A semantic vocabulary, never a layout**: ordered sequences, quotes,
  callouts, table captions, subtitles; slides that declare what they are
  (`content`, `section`, `comparison`, `table`).
- **Pure renderers, zero new dependency**: csv stdlib (`utf-8-sig` BOM for
  Excel), openpyxl, python-docx, python-pptx, PyMuPDF Story.
- Cards below the response via the SSE done chunk and `message_metadata`, ONE
  serializer (`document_store.to_wire_metadata`).
- **Honest failure**: a truncated model output is refused, never rescued into a
  shorter document (ADR-275).

## Architecture

```
generate_document tool (guards: user, flag, doc_type enum)
  └─ generate_document_for_user
       ├─ prompt_values           # budgets published to the writer (ADR-184)
       ├─ get_structured_output_with_retry(user_id=…)   # both ceilings apply
       │    └─ StructuredOutputTruncatedError → DocumentOutputTruncatedError
       ├─ build_render_context    # reader's language, timezone, page size
       ├─ render_document → normalize_content → RENDERERS[doc_type]
       ├─ Attachment row (TTL purge)
       └─ document_store.store_pending_document
```

### Modules

| Module | Responsibility |
|---|---|
| `schemas.py` | The vocabulary the model may speak. No bound: everything is repaired downstream. |
| `context.py` | `RenderContext` — for whom (language, timezone), where (page size), how much apparatus (`auto` / `plain`). |
| `normalize.py` | The canonical form: effective kinds, clamped levels, leaked markdown, ragged rows, characters XML forbids. Idempotent (pinned over the corpus). |
| `inline.py` | `**bold**` / `*italic*` / code / links → spans, shared by docx, pptx and pdf. |
| `tables.py` | Column typing by unanimity, legal headers, generated Excel names, chunking. |
| `fit.py` | Text measurement, calibrated against PowerPoint (see below). |
| `typography.py` | The ONE place a look is decided: sizes, greys, geometries, built-in style ids, the PDF stylesheet. |
| `renderers/` | One module per format, plus `docx_ooxml`, `docx_styles`, `pptx_geometry`, `pptx_tables`, `pdf_layout`. |
| `core/i18n_documents.py` | The handful of words a renderer writes itself, in the six languages. |

## The craft, format by format

**DOCX** — A4 or Letter; **named styles only**, redefined neutrally, so a
reader can restyle the document from Word's gallery. Title block, running head,
`PAGE`/`NUMPAGES` footer. Long documents get a pre-rendered table of contents
(live links, no page numbers until F9), native heading numbering (1 / 1.1 /
1.1.1) and a page break before each part. Numbered lists restart per list.
Tables carry a caption, a repeated header row and right-aligned numeric
columns. The East-Asian face is declared so CJK never falls back.

**PPTX** — **16:9 landscape**, by scaling the default template's owned
transforms. A layout per kind: Title Slide, Section Header, Title and Content,
Comparison, Title Only + native table. A slide number on every slide but the
cover. **Nothing overflows**: bodies are measured, shrunk to 14 pt, then split
into "Title (2/3)" slides; an oversized bullet is cut at sentence boundaries.
Tables are chunked with their header repeated, in a greyscale built-in style.

**XLSX** — columns TYPED by unanimity (int, decimal, percentage, date,
datetime; one stray value keeps the column text, and a leading zero protects a
code), each with its number format; header row bold, wrapped and frozen; a
named Table gives Excel its filter and banding; widths computed and bounded.

**PDF** — a stylesheet built from `typography`; title block; running head and
footer stamped on every page **with a font that has the glyphs they need**
(Helvetica is asked first; a Chinese title fell back to `······` before, on
every page, while the body was perfect — the Story embeds its own CJK
fallback, the stamps did not); long documents get a contents **on its own page**
with EXACT numbers plus PDF bookmarks and links. Tables carry no header
background (the MuPDF phantom rectangle), banded rows instead, and a **wide
table is shrunk by a measured ladder**: MuPDF sizes columns from their content
and honours neither `width: 100%` nor `table-layout: fixed`, so 12 columns
reach 714 pt on a 595 pt page at the base size. ≤ 8 columns keep it, 9-10 take
9 pt, 11-12 take 7 pt, 13-16 take 6 pt.

**MD / TXT / CSV** — the vocabulary rendered in each syntax; csv unchanged
(BOM + formula neutralization).

## The fit estimator

python-pptx computes no autofit, PowerPoint applies none on open, and
`fit_text` is wrong by a factor of two — so the renderer measures the text
itself. Calibrated 2026-09-08 against PowerPoint 16, 54 combinations on the
16:9 body frame:

- any average glyph width in **[0.426, 0.493] em** counts every line exactly
  (`AVG_CHAR_WIDTH_EM = 0.46`, near the middle of that interval);
- `lines × size × 1.2 + paragraphs × size × 0.2`, times **1.05**, gives **0
  under-predictions**.

**A full-width glyph is one em, by definition** — every calibration measurement
was Latin, and counting an ideograph at the Latin width measured a dense
Chinese slide at 238 pt where it takes 442 pt in a 356 pt frame. PowerPoint
reports **2 overflows on that deck under the Latin width, one of 124.1 pt, and
0 under the corrected one**. `text_width_em` is the single notion of width; a
Latin string still measures `len × 0.46`, so the calibration is untouched.
`display_columns` expresses the same width in average Latin characters — the
unit Excel sizes a column in, and the one a proportional pptx table weight
needs.

The 54 measurements are the fixture of `test_fit.py`. **Stated limit**: these
are Calibri metrics; Carlito is metric-compatible, other viewers substitute.

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DOCUMENT_GENERATION_ENABLED` | `true` | Deployment ceiling; gates catalogue + tool registration |
| `DOCUMENT_GENERATION_RATE_LIMIT_CALLS` / `_WINDOW` | 10 / 300 s | Per-user sliding window on the tool |
| `DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS` | 120.0 | Executor floor (ADR-160 family) |
| `MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS` | 480.0 | Executor ceiling |
| `DOCUMENT_GENERATION_MAX_SOURCE_CHARS` | 60000 | `source_data` cap (truncation reported) |
| `DOCUMENT_GENERATION_PAGE_SIZE` | `a4` | docx/pdf page size (`a4` or `letter`) |
| `DOCUMENT_GENERATION_TOC_MIN_HEADINGS` | 5 | Headings from which the long-document apparatus switches on |
| `DOCUMENT_GENERATION_SLIDE_MAX_BULLETS` | 6 | Slide density budget, published and enforced |
| `DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS` | 110 | Bullet length budget, published and enforced |

### Switches (two levels)

1. Env flag `DOCUMENT_GENERATION_ENABLED` (deployment ceiling).
2. Admin runtime capability `PlatformCapability.DOCUMENT_GENERATION`.

There is deliberately NO per-user opt-in (owner decision 2026-08-18).

### Admin LLM Config

Slot `document_generation` (category Specialized, power tier high): provider,
model, temperature, `max_tokens` — which also sets the **length budget the
prompt publishes** — and timeout are admin-tunable.

The budget is **per content family**, because they do not have the same
economics. Measured 2026-09-08 with `o200k_base` on realistic large documents:
prose and slides converge to **0.69 words per output token**, a workbook to
**0.25** (short cells make the JSON structure dominate).
`DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN` therefore declares 0.55 for
`SectionedContent` and `SlideContent` and 0.20 for `TabularContent`, each about
20 % under its measurement. A single factor published a number **2.2× too
generous for a spreadsheet** — a model obeying the budget it was given would
still have been cut at it.

## The corpus and the measurement harness

A test can prove a file opens; it cannot prove it is well composed. Thirteen
deterministic documents (`tests/fixtures/document_corpus/`) are rendered in
every applicable format by the unit tests, and:

```bash
task documents:corpus:render     # writes them to apps/api/data/document_corpus_out/
task documents:corpus:measure    # Windows: asks Word, PowerPoint and Excel
```

The measurement reports slide overflows, Word's computed fields and contents,
heading numbering, and whether Excel opens each workbook without repair. It is
a MEASUREMENT, never a gate (CI has no Office) — the `mobile:probe` shape.

Measured 2026-09-08 after implementation: **0 overflows on 69 slides**, all
960 × 540 pt; `Page 1 / 10` and `第 1 页，共 7 页` computed by Word; contents on
the long documents only; every workbook opened.

## Stated limits

- Word's contents shows no page numbers until the reader presses F9 (the
  alternative is a dialog on every open, or invented numbers).
- The estimator is calibrated on Calibri metrics.
- A Chinese PDF weighs about **3.9 MB**: the embedded CJK face dominates and
  `subset_fonts()` does not shrink what the Story embedded.
- Integers carry no thousands separator: a year and a postal code are integers
  too.
- **Beyond 16 columns a PDF table overflows the page**, whatever the font size
  (20 columns overflow even at 5 pt, and a table that narrow is unreadable
  anyway). The constant `PDF_TABLE_MAX_FITTING_COLUMNS` states it rather than
  the renderer pretending otherwise.
- The word budget is meaningless in a language that does not separate words:
  Chinese text measures ~0.04 "words" per token, so the published number cannot
  bound it. A truncation there is caught by ADR-275 and reported honestly
  rather than silently shortened.
- The slides and sectioned families are outside OpenAI's strict mode (nesting
  depth 6): a table inside a repeated block costs two levels. `SectionedContent`
  has been there since ADR-226; the verdict is measured and pinned per family.

## Why not…

- **A vendored `.dotx`/`.potx` template**: an identity, opaque to review, and
  it drifts.
- **A layout catalogue chosen by the model**: a drawing decision the model
  cannot judge.
- **`python-pptx.fit_text`**: measured wrong by a factor of two.
- **A new PDF dependency**: the Story engine plus a two-pass layout gives exact
  page numbers with what is already installed.
