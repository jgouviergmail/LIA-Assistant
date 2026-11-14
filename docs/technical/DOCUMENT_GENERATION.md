# AI Document Generation (ADR-226, ADR-274, ADR-388)

> Downloadable documents (csv, xlsx, docx, pptx, pdf, md, txt) written by a
> dedicated LLM slot, rendered locally, stored as TTL attachments and delivered
> as cards below the assistant response. Architectural mirror of
> [IMAGE_GENERATION.md](./IMAGE_GENERATION.md).
>
> **The craft belongs to the renderer, the meaning to the model** (ADR-274):
> the model says what a thing IS; the renderer decides how it is drawn, with
> the native mechanisms of each format — formulas Excel recomputes, charts a
> presenter restyles, fields Word computes, links a reader opens (ADR-388).

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
  (docx/pdf/md/txt), slides (pptx). The writer reads the rules of ITS family
  only.
- **A semantic vocabulary, never a layout**: ordered sequences, quotes,
  callouts, captions, key figures, pictures, cited sources; slides that declare
  what they are; columns that declare what their values are (an amount and its
  currency, a percent, a year, a code) and how they are computed.
- **Every closed vocabulary is published, then repaired, never refused**: a
  word off the list (a tone, a pictogram, a chart form) is mended at
  normalization; one refused word would cost the whole document, three paid
  times (ADR-269).
- **Computed, never typed**: a computed column is a formula from one grammar,
  written live in a workbook and as its exact value everywhere else.
- **Charts in every format**, each in its native mechanism.
- **A palette by tone** (`sober`, `institutional`, `warm`, `technical`), every
  colour validated; a document with no tone keeps its grey.
- **Pictures the person allows**: illustrations drawn by the configured image
  model, within a budget, billed to the turn (ADR-305).
- Cards below the response via the SSE done chunk and `message_metadata`, ONE
  serializer (`document_store.to_wire_metadata`).
- **Honest failure**: a truncated model output is refused, never rescued into a
  shorter document (ADR-275); a picture that fails is left out and said.

## Architecture

```
generate_document tool (guards: user, flag, doc_type enum)
  └─ generate_document_for_user
       ├─ _for_format             # a format that places no picture asks for none
       ├─ prompt_values           # budgets and rules published to the writer (ADR-184)
       ├─ get_structured_output_with_retry(user_id=…)   # both ceilings apply
       │    └─ StructuredOutputTruncatedError → DocumentOutputTruncatedError
       ├─ build_render_context    # reader's language, timezone, page size, preferences
       ├─ normalize_content       # canonical form, pictures within the budget
       ├─ draw_illustrations      # the image slot, billed per picture (ADR-305)
       ├─ render_document → RENDERERS[doc_type]
       ├─ Attachment row (TTL purge)
       └─ document_store.store_pending_document
```

### Modules

| Module | Responsibility |
|---|---|
| `schemas.py` | The vocabulary the model may speak. No bound: everything is repaired downstream. |
| `context.py` | `RenderContext` — for whom (language, timezone), where (page size), how much apparatus (`auto` / `plain`), the person's preferences, the pictures drawn. |
| `normalize.py` | The canonical form: effective kinds, clamped levels, leaked markdown, ragged rows, vocabularies repaired, pictures within the budget, sources in their place. Idempotent (pinned over the corpus). |
| `columns.py`, `formulas.py`, `computation.py`, `numbers.py` | What a column is; the one formula grammar, read as Excel text and as an exact value; the computed table; how a typed value reads in the reader's language. |
| `workbook_figures.py` | A workbook's key figures: settled against the canonical sheets and inputs, computed once each, after the figures they read. |
| `charts.py` | A chart: the intent the writer states, the form the data can bear. |
| `inline.py` | `**bold**` / `*italic*` / code / links → spans, shared by docx, pptx and pdf; an address is a span of its own, which a rich renderer makes clickable. |
| `tables.py` | Column typing by unanimity, legal headers, generated Excel names, chunking. |
| `fit.py` | Text measurement, calibrated against PowerPoint (see below), and the balanced rows a figure band and a figure slide share. |
| `typography.py` | The ONE place a look is decided: sizes, greys, palettes by tone, geometries, built-in style ids, the PDF stylesheet. |
| `pictures.py`, `illustrations.py`, `icons.py`, `raster.py` | How many pictures a document may carry and what a drawn one is; drawing them; the closed set of pictograms; the one SVG → PNG door. |
| `renderers/` | One module per format, plus the shared pieces: charts (`chart_svg`, `chart_scale`, `pptx_charts`, `xlsx_charts`), pages (`page_figures`, `page_pictures`), decks (`pptx_figures`, `pptx_pictures`, `pptx_motion`, `pptx_geometry`, `pptx_tables`), Word (`docx_ooxml`, `docx_styles`), the PDF layout (`pdf_layout`), workbooks (`xlsx_parts`, `xlsx_figures`), themes (`office_theme`). |
| `core/i18n_documents.py` | The handful of words a renderer writes itself, in the six languages. |
| `core/document_preferences.py` | The person's choices (illustrations, animations), read through ONE door. |

## The craft, format by format

**XLSX** — written by XlsxWriter (openpyxl cached no formula value: a reader
saw `None`). Columns TYPED by the kind the writer declared or by unanimity (an
amount with its currency, a percent, a date, a year with no thousands
separator, a code that keeps its leading zero), each with its number format. A
percentage is written with its sign: plain numbers declared `percent` read as the
workbook reads them — fractions, `0.2` for 20 % — only when every one of them is
a fraction, and the declaration goes otherwise (`20` was shown « 2 000 % »), in
every format (`columns.reads_as_percent`). A
named Table gives Excel its filter, its sort and its banding; the header row is
frozen. A **computed column is a live formula** written with the value it
computes, because many readers never recalculate — a preview pane, a phone,
the chat's own excerpt; the totals row is the Table's own, its cached totals
given explicitly. Assumptions sit on a first sheet as defined names the
formulas read; the **key figures** follow them on a sheet of their own, each a
live formula named like its label, with its cached value; a summary by group is
a sheet of `SUMIFS` reading the data; a
column with a closed list of values gets a drop-down (read from a hidden sheet
when it is too long to write inline, or holds a comma or a quote); a measure that has a
good direction gets a colour scale; a native chart reads the sheet's own cells
(a hidden sheet turns an empty cell into a gap, never a zero). Printing is set:
landscape when the table is wide, one page wide.

**PPTX** — **16:9 landscape**, by scaling the default template's owned
transforms; the theme recoloured in the document's tone. A layout per kind:
title, part opener (in the accent, with a pictogram or a picture), content,
comparison, native table, **native chart** (editable, its data embedded), key
figures as **tiles** (balanced rows: six read 3 + 3), a **quote** beside a rule.
An **agenda** is added from several parts; never written by the model. A slide
number on every slide but the cover. **Nothing overflows**: bodies are
measured, shrunk to 14 pt, then split into "Title (2/3)" slides; an oversized
bullet is cut at sentence boundaries; a row of tiles or a quote that cannot fit
falls back to bullets, which split. A deck the writer declares **presented**
moves by the person's choice (Settings › Documents): sober fade transitions
and points revealed one at a time, written as PresentationML; a deck to read
stays still.

**DOCX** — A4 or Letter; **named styles only**, so a reader can restyle the
document from Word's gallery. Title block, running head, `PAGE`/`NUMPAGES`
footer. A long document opens on a **cover page** (title, subtitle, date, its
picture; Word's « different first page » keeps it unstamped), then a
pre-rendered table of contents (live links, no page numbers until F9), native
heading numbering (1 / 1.1 / 1.1.1) and a page break before each part. Key
figures are a **band of shaded tiles**; charts are figures at the text width
(PNG with their words as alternative text) and pictures are figures too,
numbered together. A table of eight columns or more takes **landscape pages of
its own** — the heading that announces it turns with it — and the document
turns back for what follows. Every printed address is a **hyperlink**, and the
sources the text cites as [n] close the document, numbered, each with its
link. Numbered lists restart per list; tables carry a caption, a repeated
header row and right-aligned numbers. The East-Asian face is declared so CJK
never falls back.

**PDF** — a stylesheet built from `typography`; running head and footer
stamped **with a font that has the glyphs they need** (Helvetica first; a
Chinese title fell back to `······` before, on every page). A long document
opens on an **unstamped cover**, then a contents page with EXACT numbers, plus
PDF bookmarks and links. Every figure — a chart, a picture — is laid out as an
empty **room** of its exact size and drawn into it afterwards: a chart as
vectors whose words stay text, a picture as the JPEG it is. A figure the Story
squeezed at a page's end gets a page of its own on the next pass, with the
heading that announces it. Key figures are a band of tiles; every printed
address is a **clickable link** — the Story writes none, it reports where each
word of an `<a>` landed, and the words are joined line by line into links.
Tables carry no header background (the MuPDF phantom rectangle), banded rows
instead, and a **wide table is shrunk by a measured ladder**: MuPDF sizes
columns from their content and honours neither `width: 100%` nor
`table-layout: fixed`, so 12 columns reach 714 pt on a 595 pt page at the base
size. ≤ 8 columns keep it, 9-10 take 9 pt, 11-12 take 7 pt, 13-16 take 6 pt.

**MD / TXT** — the vocabulary in each syntax: a chart becomes the table of the
values it draws, key figures are listed value first, the sources close the
document (links in Markdown, addresses spelled out in text). Neither can hold
a picture: its writer is asked for none. **CSV** — data for another program:
BOM, formula neutralization, computed columns as values, no totals row, no key
figures.

## One formula grammar

A computed column's `formula` names the columns of its own table — and, in a
workbook, its inputs — between braces. The grammar (`formulas.py`) has the
arithmetic (`+ - * / ^`, parentheses), `ROUND`, `ABS`, `MIN`, `MAX`, a whole
column's `SUM` and `AVERAGE`, `RUNNING_SUM` (the column from its first row down
to this one), `PREVIOUS` (the row above), and `IF(condition, value, value)`
where a condition compares two numbers (`= <> < <= > >=`) or a text column with
a quoted text (`=` or `<>`), joined by `AND`, `OR`, `NOT`. A function name reads
whatever its case, `==` and `!=` read as `=` and `<>`. Nothing is executed:
`ast` parses, every node outside the grammar is refused, and one tree gives
both the Excel text and the exact value.

The cached value must be the one Excel recalculates, so where Excel is not
arithmetic its reading is mirrored:

- an empty cell is 0 in arithmetic and in a comparison, and is skipped by an
  aggregate, a running sum, and `MIN` or `MAX` through a bare reference —
  including one an `IF` returns, since Excel's `IF` returns the reference it
  chooses;
- `IF` computes only the value it chooses; `AND` and `OR` read every condition;
- two numbers compare on 15 significant digits (Excel's rule, documented by its
  community rather than by Microsoft), a text without case and as the workbook
  holds it — ADR-226's quote included;
- a computed cell with no value is an empty TEXT in the workbook
  (`IFERROR(…,"")`): whatever reads it in arithmetic has no value either and is
  wrapped too (`blank_columns`), a chart reads it through its gap-safe copy,
  and a comparison never reads it bare, since Excel would find a text larger
  than any number. Nor does a comparison read the row above bare: the first
  row's is the header.

A column never reads itself: in its own formula its name is the input of that
name — a writer names a column after the input it shows, `Rent` computed as
`{Rent}` — or the formula is refused (`reads_itself`).

What cannot be computed is dropped at normalization, never refused (ADR-184):
an unknown name, a text read as a number, a number compared to a text, a
formula longer than the published bound, a cycle — whose members alone lose
their formula. No value is ever computed from a computation that failed: the
column keeps the cells the writer wrote, or goes when nothing was written in
it, and every formula reading a column that goes fails in turn. A column the
writer leaves empty without a formula is data: a formula reads it as zero.

A value every reader can show, or none: a result past what Excel holds
(9.99E+307, where the workbook answers `#NUM!` and no float could be cached) is
a row without value, a literal no float holds (`1e999`) is outside the grammar,
and a computed date no calendar holds is an empty cell (the workbook shows
`#####`). A long number is written whole, and a negative one keeps its sign
through the rounding of the number it stands before (-0.005 reads -0.01, as in
the workbook). An input is a number or a date, like a key figure: a kind that
would write its cell as a text (`text`, `code`) reads « inferred », since Excel
compares a text as larger than any number.

### A workbook's key figures

A column's formula is the same for every row and reads its own sheet: a
summary whose rows are different quantities — a year's income, the expenses of
every month, the share they leave — is out of its reach. The writer declares
those as `figures`, each a `label`, a `formula`, a `kind` (a number or a date,
never a text) and a `unit`. A figure's formula has the grammar with no row: it
reads the inputs and the other figures by name, and a sheet's whole column as
`SUM({Sheet/Column})` or `AVERAGE({Sheet/Column})` — the sheet's name and the
column's, the split found at whichever slash names both.

- **Settled at normalization** (`workbook_figures.normalize_figures`), against
  the canonical sheets and inputs: a figure with no label or formula, a
  repeated label, one past `DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX`, a row
  read, a text column, an unknown name and a cycle's members go, then every
  figure reading one that went, until nothing changes. An input wins over a
  figure of its name, and in its own formula a figure's name is that input's.
- **Computed once** (`compute_figures`), each after the figures it reads. A
  figure with no value — a division by zero, an average of nothing — is an
  empty text in the workbook, as a computed cell is, and held to a column's
  rules: `MIN` and `MAX` skip it (a defined name is a reference), arithmetic on
  it has no value either, and no comparison reads bare a figure that may have
  none — normalization drops the figure that would.
- **Written live** (`renderers/xlsx_figures.py`) on a sheet reserved before the
  data sheets and filled after them: one Table of a label and a value per
  figure, each value a defined name (`Annual_income`) that the other figures
  read, its whole-column reads absolute ranges (`'Monthly budget'!$C$2:$C$13`),
  its cached value the one computed, wrapped in `IFERROR(…,"")` where it may
  have none. A defined name never takes a table's shape (`Table1`), since Excel
  holds tables and names in one namespace, nor the prefix of Excel's own names
  (`_xlnm.`).

## Colour: a palette by tone

The writer gives the document a `tone`; `typography.PALETTES` says it in
colours. An **accent** marks structure — the title, the two largest heading
levels, rules, a part opener, a figure's value — and never small text, since
some accents hold 3:1 on paper, not 4.5:1. A link's ink is the accent where it
holds 4.5:1 and ink otherwise, underlined either way. Series colours are
assigned in a fixed order validated for colour-blind readers (every slot ≥ 3:1
on paper, adjacent pairs far apart under protanopia and deuteranopia); a label
inside a fill takes the ink that contrasts more. **A document with no tone
keeps the grey it always had** — meeting minutes among them, unchanged.

## Pictures

An illustration is an image generation (ADR-305), so it exists only when:

1. the person's image generation is on, and their choice in **Settings ›
   Documents** is not « never » (`auto` lets the writer judge; `on_request`
   waits for the request to ask);
2. the format places pictures (pptx, docx, pdf);
3. the document is within `DOCUMENT_ILLUSTRATIONS_MAX` — ONE budget
   (`pictures.illustration_budget`), published in the prompt's tail and
   enforced by normalization (the cover first, then in order);
4. both spend ceilings answer yes, asked before the first picture.

The writer gives each picture a subject in English and its alternative text in
the document's language, and the document ONE visual style. The pictures are
drawn a few at a time (`DOCUMENT_ILLUSTRATION_CONCURRENCY`), at the person's
quality and in the size tier they chose, the frame deciding the proportions
(`edit_size`), all within one call's time of the image slot (the tool's step
declares both slots: `TOOL_LLM_SLOTS`); each is billed to the turn the moment
the vendor bills it, through the call the image tool shares
(`image_generation/billed_call.py`). A picture that fails is left out, its
place laid out without it, and the tool's message says how many were drawn and
why the others were not — by facts, never by an error's words (ADR-303).

## Measurements

```bash
task documents:corpus:render     # writes the corpus to apps/api/data/document_corpus_out/
task documents:corpus:measure    # Windows: asks Word, PowerPoint and Excel
task documents:writer:measure -- --models provider:model@level --budget 1   # PAID
```

A test can prove a file opens; it cannot prove it is well composed. The
deterministic documents of `tests/fixtures/document_corpus/` are rendered in
every applicable format by the unit tests (pictures drawn flat). The Office
measurement reports slide overflows, Word's computed fields and contents,
heading numbering, transitions and reveals, charts, and whether Excel opens
each workbook without repair. Both are MEASUREMENTS, never gates (CI has no
Office) — the `mobile:probe` shape.

The **writer measurement** runs the scenarios of
`apps/api/scripts/document_generation/writer_scenarios.json` through the
production's own door on the models passed, pointed at in its own process (the
database is never written), on the proof account: calls (a refused answer is
paid again), tokens, cost, seconds, and the rules the writer kept — figures
found in the material, no invented address, pictures within the budget, a
presented deck declared so, formulas the grammar accepts (a workbook's key
figures counted among them), every column delivered with a value. It prints
counts and flags, never a document. ADR-388 records what it measured.

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

## Where a generated document lives afterwards (ADR-279)

A rendered document is stored as an `Attachment` stamped
`origin = generated_document`, carrying the `title` the model gave it and the
`conversation_id` it came from. It is listed by Settings → « My generated
files », documents gallery (`GET /generated-assets?family=documents`), where it
can be searched by name, downloaded and removed.

**A document carries no marker of its own in its filename** — the generator
names it after the person's request — so the migration that backfilled the
column for pre-existing rows recognised documents from the MESSAGE METADATA
pointing at them, never from a name. Anything neither pass proved stays
`upload`, which is what the row already was.

The retention is unchanged (24 h by default): the gallery states each deadline,
it does not extend it.

---

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
| `DOCUMENT_ILLUSTRATIONS_MAX` | 6 | Pictures one document may carry, each an image generation billed to the turn; 0 switches illustrations off |

### Switches and choices

1. Env flag `DOCUMENT_GENERATION_ENABLED` (deployment ceiling).
2. Admin runtime capability `PlatformCapability.DOCUMENT_GENERATION`.
3. Per person, **Settings › Documents**: illustrations (`auto` by default,
   `on_request`, `never`) and animations of a deck (`presented` by default,
   `always`, `never`). An illustration also needs the person's image
   generation on and the image capability offered by the instance.

There is deliberately NO per-user opt-in to the tool itself (owner decision
2026-08-18).

### Admin LLM Config

Slot `document_generation` (category Specialized, power tier high): provider,
model, temperature, `max_tokens` — which also sets the **length budget the
prompt publishes** — and timeout are admin-tunable. The pictures run on the
`image_generation` slot.

The budget is **per content family**, because they do not have the same
economics. Measured 2026-09-08 with `o200k_base` on realistic large documents:
prose and slides converge to **0.69 words per output token**, a workbook to
**0.25** (short cells make the JSON structure dominate).
`DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN` therefore declares 0.55 for
`SectionedContent` and `SlideContent` and 0.20 for `TabularContent`, each about
20 % under its measurement. A single factor published a number **2.2× too
generous for a spreadsheet** — a model obeying the budget it was given would
still have been cut at it.

## Interactive pages have a slot of their own

A page the person will use (a game, a quiz, a calculator) is not a document: it runs in the chat,
in a sandboxed frame, and only its `.html` file joins the documents, through the same
`store_document`. See [INTERACTIVE_PAGES.md](INTERACTIVE_PAGES.md) and
[ADR-370](../architecture/ADR-370-A-Page-The-Model-Writes-Runs-In-The-Chat-In-The-Strictest-Frame.md). Its model, output budget and timeout are the
`interactive_page` slot's; the rate limit and the step family stay shared, so a change to those
here is felt there.

## Stated limits

- Word's contents shows no page numbers until the reader presses F9 (the
  alternative is a dialog on every open, or invented numbers).
- A chart in Word is a picture (PNG at 200 dpi with its words as alternative
  text): python-docx writes no chart part.
- The estimator is calibrated on Calibri metrics.
- A column's formula reads its own sheet and the inputs, not a key figure nor
  another sheet's column, though Excel reads both: that needs one dependency
  order for the whole workbook, which is not built (ADR-388). A key figure's
  whole-column functions are `SUM` and `AVERAGE` alone.
- A Chinese PDF weighs about **3.9 MB**: the embedded CJK face dominates and
  `subset_fonts()` does not shrink what the Story embedded.
- A PDF carries no tagged structure: a picture's alternative text lives in
  Word, the PDF shows its caption.
- **Beyond 16 columns a PDF table overflows the page**, whatever the font size
  (20 columns overflow even at 5 pt, and a table that narrow is unreadable
  anyway). The constant `PDF_TABLE_MAX_FITTING_COLUMNS` states it rather than
  the renderer pretending otherwise.
- The word budget is meaningless in a language that does not separate words:
  Chinese text measures ~0.04 "words" per token, so the published number cannot
  bound it. A truncation there is caught by ADR-275 and reported honestly
  rather than silently shortened.
- The three families are outside OpenAI's strict mode (nesting depth 6 to 7):
  a table inside a repeated block costs two levels, a column's declarations one
  more. The verdict is measured and pinned per family. They are outside
  Claude's strict tool use too (24 optional parameters per request; the report
  declares 33, the deck 36): a writer's mechanical slip in its arguments — a
  structure written as JSON text, a bracket that closes nothing — is repaired
  in the shared door instead (ADR-100 amendment 2026-11-13).
- Office's own verdict on transitions, reveals, charts and themes written by
  hand is the owner's measurement (`task documents:corpus:measure`); the unit
  tests read the files back with the libraries that wrote them.

## Why not…

- **A vendored `.dotx`/`.potx` template**: an identity, opaque to review, and
  it drifts.
- **A layout catalogue chosen by the model**: a drawing decision the model
  cannot judge.
- **`python-pptx.fit_text`**: measured wrong by a factor of two.
- **A new PDF dependency**: the Story engine plus a two-pass layout gives exact
  page numbers with what is already installed.
- **A chart form chosen by the model**: a pie of fifteen slices. The writer
  states what the chart MEANS; the renderer picks a form the data can bear,
  and a form the person named is kept when the data bears it.
- **Values the model computes**: it gets them wrong. It declares a formula; the
  renderer computes every value with one grammar.
