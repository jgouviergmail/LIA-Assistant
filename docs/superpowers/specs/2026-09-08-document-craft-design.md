# Document craft — design (2026-09-08)

Generated documents (docx, pptx, xlsx, pdf, md, txt, csv — ADR-226) are written
well and laid out badly. This design moves the *craft* of a document — the
conventions a professional file follows, produced with the native mechanisms of
its format — into the renderers, gives the model a small **semantic** vocabulary
(what a thing *is*, never how to draw it), and closes two honesty defects found
on the way. No brand identity, no vendored template: neutral typography, named
styles, and a guarantee that nothing overflows.

## 1. Problem

The owner's observation (2026-09-08): "the layouts are basic, unworked and
unattractive — most visibly on PowerPoint, but on every format". The prompt was
suspected. It is not the cause: the prompt already asks for more than the system
can render.

Two ceilings, both in code:

1. **The vocabulary.** `Slide` is `title + bullets + notes`; `SectionBlock.kind`
   has four values. Whatever the prompt asks, a twelve-slide deck is twelve times
   the same layout, and a report cannot hold a caption, a quote, an ordered
   sequence or a callout. ADR-184 pointing the other way: an exigence is
   *demanded* without being *expressible*.
2. **The renderer.** `pptx.Presentation()` is the stock 4:3 Office template with
   two of its eleven layouts used; `docx.Document()` uses four of 164 named
   styles; the PDF goes through PyMuPDF's Story with **no stylesheet at all**;
   xlsx gets bold headers and column widths.

"Professional" here means the codes of the document type — title block, table
of contents, numbered headings, headers and footers, real styles, captions,
repeated table headers, typed spreadsheet columns, a deck whose text fits its
frames — not decoration.

## 2. What exists (measured, not assumed)

| Piece | Where | Finding |
|---|---|---|
| Content contract | `document_generation/schemas.py` | 3 families selected per format BEFORE the LLM call (strict-compatible); `SectionBlock.kind ∈ {heading, paragraph, bullets, table}`; `Slide = title/bullets/notes` |
| Renderers | `document_generation/renderers.py` (310 lines) | pure functions, zero styling, registry completeness-asserted |
| Prompt | `prompts/v1/document_generation_prompt.txt` | 855 tokens; substance rules are good; form rules cannot be honoured |
| LLM slot | `document_generation` (`gpt-4.1`, `max_tokens=16000`) | one structured call per document, `TURN` spend road |
| Consumers | `meetings/delivery.py::render_pdf` | meeting minutes PDF goes through `render_document(PDF, SectionedContent)` |
| | `infrastructure/tabular_io/writer.py` | imports `neutralize_formula` only |
| Frontend | `GeneratedDocumentCards` | native `<a>` cards, no preview — untouched |
| PPTX template | python-pptx `default.pptx` | **4:3** (10 × 7.5 in), 11 layouts, 2 used |
| DOCX template | python-docx `default.docx` | 164 styles, 4 used; `keep_with_next` already on headings; no heading numbering; `TOC Heading` is **based on Heading 1** |
| Fonts | PyMuPDF wheel, Windows and the Linux container | Nimbus Sans + **Droid Sans Fallback (CJK)** embedded — no system font needed |

## 3. Hypotheses verified

Every mechanism below was exercised with the real libraries and, for Office
formats, measured by Word / PowerPoint / Excel themselves through COM on the
development machine. Verdicts:

| Hypothesis | Method | Verdict |
|---|---|---|
| The current PPTX renderer overflows on a dense slide | PowerPoint `BoundHeight` | **Confirmed**: 1 444 pt of text in a 356 pt frame (+1 087 pt) |
| `MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE` alone fixes it | same | **Refuted**: identical overflow, PowerPoint applies nothing on open |
| python-pptx `fit_text` is reliable | same | **Refuted**: it picked 21 pt, PowerPoint still measured +364 pt (it ignores the master's paragraph spacing) |
| A font-free estimator can be exact | 54 combinations (size × bullets × length) measured by PowerPoint | **Validated**: 0.42 em per character → **0 line-count errors**; height = lines × size × 1.2 + paragraphs × size × 0.2; ×1.05 → **0 under-predictions** |
| 16:9 by scaling the default template | scale master + layout placeholders that own an `xfrm` | **Validated** (960 × 540 pt, no overflow, slide numbers rendered). First attempt refuted: writing an inherited position freezes `y`/`cy` at 0 |
| Neutral built-in table styles by GUID | PowerPoint resolves them | **Validated**; "Light Style 1" is grayscale |
| Word TOC field is empty on open | Word COM | **Confirmed** (`len 0`); a cached result shows on open and F9 regenerates it |
| Native heading numbering | Word `ListString` | **Validated** — after detaching `TOC Heading` (it inherited the numbering and counted "Contents" as chapter 1) |
| Numbered lists restart per list | fresh `w:num` + `startOverride` | **Validated** |
| `PAGE`/`NUMPAGES` compute on open; `tblHeader` repeats; `keep_with_next` | Word COM + export | **Validated** |
| XLSX typed cells, formats, named Table, freeze, autofilter | Excel COM | **Validated** ("1 234,50", "12,0 %"). **Duplicate or empty Table headers → Excel refuses to open the file**; `1abc` accepted by openpyxl, illegal in Excel |
| PDF CSS, fonts, CJK, exact TOC | PyMuPDF on Windows **and** in the Linux container | **Validated**; exact TOC by a two-pass layout (`element_positions`) converging in one extra pass; PDF outline set |
| `th` background + `border-collapse` | drawing inventory per page | **Phantom rectangle** on continuation pages (MuPDF); `tr:nth-child(even)` banding supported |
| A truncated output is rescued as a shorter document | cut a valid payload at 100 positions | **Confirmed**: 12 report cuts and 14 deck cuts validate as SHORTER documents |
| The structured-output door resolves the account from `config` | LangGraph probe | **Refuted**: only `thread_id` is merged into `metadata`; `user_id` is not |
| Cost | tiktoken | prompt 855 tokens, schemas 193–431, outputs 1.6–2.1 k for synthetic deck/report |

## 4. Two defects found on the way

**Truncation is repaired in silence.** `json_recovery.extract_json_payload`
closes an open structure mechanically, then `_rescue_structured_from_text`
validates what is left. A document cut by `max_tokens` therefore becomes a
shorter valid document — rendered, stored, and announced "generated
successfully". `finish_reason` is read nowhere in `structured_output.py`. When
the repair does NOT validate, the call is retried three times with the same
prompt: a truncation is deterministic, so each retry is paid for nothing. ADR-226
states the opposite ("an overflow fails honestly"). Every structured caller is
affected, meeting minutes included.

**The structured-output door cannot name the account.** `resolve_owner` reads
`config["metadata"]["user_id"]`; LangGraph never puts it there. The document
service knows `user_id` and does not pass it, so at this door only the INSTANCE
ceiling is asked. Enforcement is not broken — the per-account ceiling is asked
at the turn entrance (`stream_gates`) — but the door depends on another door,
and `test_every_spend_site_is_bounded` accepts `get_structured_output_with_retry`
by name ("carrying the owner") although this call carries nothing.

## 5. Decisions

1. **The craft belongs to the renderer; the meaning belongs to the model.** The
   model says what a thing is (a sequence, a quote, a warning, a caption, a
   section opener, a comparison, data); the renderer decides how it is drawn.
   No layout catalogue, no brand identity, no vendored `.dotx`/`.potx`.
2. **Native mechanisms, not imitation.** Word: named styles, fields, numbering
   definitions, header/footer parts. PowerPoint: the template's own layouts and
   placeholders, the slide-number field, built-in table styles. Excel: typed
   cells, number formats, a named Table, freeze panes, autofilter. PDF: a
   stylesheet, outline bookmarks, links, exact page numbers.
3. **Nothing overflows, by construction.** Text is measured by a calibrated
   estimator before it is placed; what does not fit is shrunk to a floor, then
   split, never clipped and never left to the viewer.
4. **Every incoherence is repaired, none is refused** (ADR-184): effective kinds
   derived from the fields present, empty blocks dropped, ragged rows padded,
   headers made unique, model-written heading numbers stripped when the renderer
   numbers, markdown that leaked into a paragraph converted to the block it is.
   The existing `level` bound (`ge=1, le=4`) is REMOVED and clamped instead — a
   level-5 heading currently fails the whole document three times over.
   `min_length=1` on `sheets`/`blocks`/`slides` stays: a document with nothing
   has nothing to render, and that is the one deliberate refusal.
5. **What the renderer enforces, the prompt publishes** (ADR-184): slide
   density, bullet length, the TOC threshold and the length budget travel as
   placeholders read from settings, with the consequence of each overrun.
6. **One predicate decides "long document"** (headings ≥
   `document_generation_toc_min_headings`): it switches the table of contents,
   the heading numbering and the page break before each part TOGETHER — never a
   TOC on a one-page note, never numbering without a TOC. A caller may pin the
   structure to `plain`; meeting minutes do (owner decision 2026-09-08): they
   gain the running header, pagination and proper tables and keep their shape.
7. **Word's TOC is pre-rendered without page numbers** (`\n` switch, live
   links). Alternatives rejected: `updateFields` on open (a Word dialog on every
   open) and invented numbers (a count shown is a claim). The PDF TOC carries
   EXACT numbers because we paginate it ourselves.
8. **A4 by default**, `DOCUMENT_GENERATION_PAGE_SIZE=a4|letter`; slides are
   **16:9 landscape** (13.333 × 7.5 in), fixed.
9. **A truncated structured output is a refusal, never a rescue**: detected from
   the provider's own metadata before any repair, raised as a dedicated error,
   never retried, translated by the document tool into an explicit failure
   naming the budget.
10. **The document service passes `user_id` to the structured door.**

## 6. Contract — the vocabulary

All additions default; no new bound; strict-mode verdict unchanged (a test pins
it) and the set of bounded properties the model sees becomes empty (a test pins
that too).

```python
class TableSheet(BaseModel):            # unchanged
    name: str; headers: list[str]; rows: list[list[str]]

class SectionBlock(BaseModel):
    kind: Literal["heading", "paragraph", "bullets", "numbered", "quote", "callout", "table"]
    level: int = 2                      # bound removed; clamped 1..4 at normalization
    text: str = ""                      # heading / paragraph / quote / callout
    items: list[str] = []               # bullets / numbered
    table: TableSheet | None = None
    caption: str = ""                   # NEW — title of a table block

class SectionedContent(BaseModel):
    filename_stem: str; title: str
    subtitle: str = ""                  # NEW — audience / purpose line
    blocks: list[SectionBlock]          # min_length=1 (kept)

class SlideColumn(BaseModel):           # NEW
    heading: str; bullets: list[str] = []

class Slide(BaseModel):
    title: str
    kind: Literal["content", "section", "comparison", "table"] = "content"   # NEW
    subtitle: str = ""                  # NEW — section tagline / content lead line
    bullets: list[str] = []
    columns: list[SlideColumn] = []     # NEW — comparison
    table: TableSheet | None = None     # NEW — data
    notes: str = ""

class SlideContent(BaseModel):
    filename_stem: str; title: str
    subtitle: str = ""                  # NEW — cover subtitle
    slides: list[Slide]                 # min_length=1 (kept)
```

`TabularContent` is unchanged: column types are INFERRED by the renderer (§8.3),
never entrusted to the model. Class docstrings stay one line — they are sent
to the model as `description`.

### 6.1 Effective kinds (normalization, `normalize.py`)

| Declared | Fields present | Effective |
|---|---|---|
| `content` | bullets | content |
| `content` | table, no bullets | table |
| `content` | bullets + table | content slide, then a table slide with the same title |
| `content` | columns (≥ 2), no bullets | comparison |
| `section` | — | section (bullets, if any, become a content slide after it) |
| `comparison` | 2 columns | comparison |
| `comparison` | 1 column | content (that column's bullets) |
| `comparison` | ≥ 3 columns | table (headings as columns, bullets as rows, `zip_longest`) |
| `table` | table | table |
| `table` | no table | content |
| any | nothing but a title | content (title-only slide) |

Sectioned blocks: `table` without a table is dropped; `bullets`/`numbered` with
no items but a text become a paragraph; a paragraph whose lines all start with
`- `, `* `, `• ` becomes `bullets`, with `1. `/`1) ` becomes `numbered`, a
single line starting with `#{1,6} ` becomes a heading; `level` is clamped to
1..4; a heading's leading `^\d+(\.\d+)*[.)]?\s+` is stripped when the document
will be numbered; empty blocks are dropped; a `caption` on a non-table block is
ignored. Tables: headers stripped; empty header → localized "Column {n}";
duplicates suffixed " (2)", " (3)"…; ragged rows are WIDENED to the longest
row (a cell beyond the headers gets a generated header — visible and
repairable, where truncation would lose what the model wrote); blank rows
dropped; headers absent but rows present → generated headers; nothing at all
→ dropped.

## 7. Architecture

```
domains/document_generation/
  schemas.py            vocabulary (§6)
  context.py            RenderContext(language, timezone, page_size, generated_at: datetime | None,
                                      structure: "auto" | "plain") + build_render_context(user, settings)
  normalize.py          canonical form (§6.1) — pure, total, table-tested
  inline.py             **bold**, *italic*/_italic_, `code`, [text](url) → spans; orphan markers literal
  typography.py         ONE type scale, neutral palette, page/slide geometries, built-in style ids, CSS builder
  fit.py                calibrated estimator: lines, height, body/title size, greedy split, sentence split
  tables.py             column typing by unanimity, header/row sanitizing, Excel-legal names, row chunking
  renderers/__init__.py RENDERERS registry (ADR-085 assert) + render_document(doc_type, content, context=None)
  renderers/text.py     csv / md / txt
  renderers/xlsx.py
  renderers/docx.py     + docx_ooxml.py (fields, numbering, TOC, shading — raw OOXML helpers)
  renderers/pptx.py     + pptx_geometry.py (16:9 scaling, placeholder lookup, slide number clone)
  renderers/pdf.py      + pdf_layout.py (two-pass Story layout, stamping, outline, links)
  sanitize.py, service.py, prompts.py, delivery.py, document_store.py   (roles unchanged)
core/i18n_documents.py            renderer-generated labels × 6 languages
core/config/document_generation.py   4 new settings; core/constants.py their defaults + WORDS_PER_OUTPUT_TOKEN
infrastructure/llm/output_truncation.py   is_output_truncated(message) + StructuredOutputTruncatedError
apps/api/scripts/document_generation/render_corpus.py, measure_office.ps1   harness (§16.3)
apps/api/tests/fixtures/document_corpus/*.json                              corpus
```

Rules the architecture obeys:

- `_call_document_llm` STAYS in `service.py`: `LLM_SPEND_ROADS` names that
  module (`TURN`), and the guard refuses a stale entry.
- `document_generation` imports nothing from `agents` (F009 cycle ratchet);
  labels and dates come from `core`.
- Every module under 600 logical SLOC; no function with cyclomatic complexity
  ≥ 15 — block and slide kinds dispatch through dictionaries, never `elif`
  chains.
- Rendering constants live in `typography.py`, the one source every renderer
  reads (the `field_mapping.py` doctrine: a cohesive data module IS the
  centralisation); tunables live in settings.
- `render_document(doc_type, content, context=None)`: the context is optional
  with a neutral default so `meetings/delivery.py` keeps working; that call site
  is updated to pass its language and `structure="plain"`, `generated_at=None`
  (the minutes carry their own dates).

### 7.1 Settings and constants

| Env var | Setting | Default | Meaning |
|---|---|---|---|
| `DOCUMENT_GENERATION_PAGE_SIZE` | `document_generation_page_size` | `a4` | `a4` or `letter` for docx and pdf |
| `DOCUMENT_GENERATION_TOC_MIN_HEADINGS` | `document_generation_toc_min_headings` | 5 | headings from which a document is "long" (TOC + numbering + part breaks) |
| `DOCUMENT_GENERATION_SLIDE_MAX_BULLETS` | `document_generation_slide_max_bullets` | 6 | published density budget; beyond it the renderer splits |
| `DOCUMENT_GENERATION_SLIDE_MAX_BULLET_CHARS` | `document_generation_slide_max_bullet_chars` | 110 | published bullet length; beyond it the renderer shrinks then splits |

Constants (not tunables): `DOCUMENT_GENERATION_WORDS_PER_OUTPUT_TOKEN = 0.55`
(the published length budget is `max_tokens × 0.55` words — JSON overhead and
the token/word ratio), the typographic floor 14 pt, the calibration constants
of §9. Declared in `.env.example` and `.env.prod.example` (hygiene gate).

### 7.2 Localized labels (`core/i18n_documents.py`)

Data module (ratchet-exempt like `i18n_effects`), the SAME key set under each
of `fr, en, de, es, it, zh-CN`, one completeness test:

| Key | fr | en |
|---|---|---|
| `documents.toc_heading` | Sommaire | Contents |
| `documents.page_of` | Page {page} / {total} | Page {page} of {total} |
| `documents.table_label` | Tableau {n} | Table {n} |
| `documents.column_label` | Colonne {n} | Column {n} |

`page_of` is split around its placeholders so Word receives text runs and
`PAGE`/`NUMPAGES` fields in the language's order. Dates come from
`core.time_utils.format_date_only(generated_at, timezone, language)` — the
user's timezone from the tool, never a literal (timezone guard). Continuation
labels are numeric — "Title (2/3)" — and need no translation.

## 8. Rendering per format

Common to docx, pptx, pdf: inline spans (§7 `inline.py`) become runs; md passes
markup through; txt strips markers; spreadsheet cells are data and are never
parsed. Every renderer consumes the normalized content (§6.1), never the raw
model output.

### 8.1 DOCX

- Page from the setting (A4: 2.5 cm margins; Letter: 1 in). Core properties:
  title, subject = subtitle, created = `generated_at`, language.
- **Named styles only**, redefined once from `typography.py`: Normal (Calibri
  11 pt, 1.15, 6 pt after, widow control), Title 26 pt, Subtitle muted, Heading
  1–4 (18/14/12/11 pt, dark grey, bold, `keep_with_next` from the template),
  Body Text, Caption, Quote (grey italic, indented), List Bullet, List Number,
  Header, Footer; East-Asian font declared so CJK never falls back to a Latin
  face. A custom paragraph style `Callout` (Normal + `w:shd` fill, left `w:pBdr`,
  indents). The Title's theme-coloured bottom border becomes a grey rule.
- Title block: Title, Subtitle (if any), date line (if `generated_at`). Running
  header = document title (Header style); footer = localized "Page X / Y" from
  `PAGE` / `NUMPAGES` fields (computed on open, verified).
- Long documents (§5.6): `TOC Heading` detached from numbering and outline
  (`numId 0`, `outlineLvl 9`); a `TOC \o "1-3" \h \z \u \n` field whose cached
  result is one paragraph per heading, styled `TOC 1/2/3` (created if the
  template lacks them: Normal + 0/0.75/1.5 cm indents), number + tab + text
  exactly as Word regenerates it; page break after; `page_break_before` on
  every Heading 1 except the first. Heading numbering: one multilevel
  `abstractNum` bound to Heading 1–3 through `pStyle`, `numPr` on the three
  styles (1 / 1.1 / 1.1.1). `plain` structure: none of this.
- Lists: List Bullet; List Number with a fresh `w:num` (+ `startOverride 1`) per
  list so every sequence restarts.
- Tables: Caption paragraph above when a caption exists ("Table {n} — caption");
  a non-accent built-in style (chosen from the corpus render, named in
  `typography.py`), `tblLook` first row on / first column off / banded rows,
  header row `tblHeader` (repeats across pages, verified), autofit to window,
  numeric columns (§8.3 typing) right-aligned.

### 8.2 PPTX

- **16:9 landscape** by scaling: `slide_width = 13.333 in`, every master shape
  and every layout placeholder that OWNS an `xfrm` has `x` and `cx` scaled by
  4/3; inherited placeholders follow the master (verified; a test pins
  960 × 540 pt and width > height).
- Layouts by effective kind: cover → `Title Slide` (title; subtitle placeholder
  = subtitle and/or date line, date run smaller and muted); `content` →
  `Title and Content`; `section` → `Section Header` (title run `cap="none"`,
  tagline in the text placeholder); `comparison` → `Comparison` (idx 1/3
  headings, 2/4 bodies); `table` → `Title Only` + native table.
- Slide number on every slide but the cover: the layout's `SLIDE_NUMBER`
  placeholder cloned into the slide (PowerPoint renders the field — verified).
- Body text: base size by bullet count (≤ 3 → 24 pt, 4–6 → 20 pt, more →
  18 pt), reduced in 2 pt steps down to 14 pt by the estimator (§9), then
  **split** into "Title (k/n)" slides by greedy fill; a single bullet that does
  not fit alone at 14 pt is cut at sentence boundaries, then words, into
  consecutive bullets — never truncated. Comparison bodies use the half-width
  geometry. Titles: 40 pt base, reduced to 24 pt; from 36 pt two lines are
  allowed inside the 90 pt title frame.
- Tables: "Light Style 1" (grayscale GUID, verified), first row on, banding on,
  first column off; header bold; numeric columns right-aligned; 12 pt (10 pt
  beyond six columns); rows per slide from the row-height budget of the body
  area; chunks become "Title (k/n)" slides, each with the header row.
- Speaker notes written whenever present, on every kind.

### 8.3 XLSX

- Column typing **by unanimity** (`tables.py`; a column converts only if every
  non-empty cell matches the same rule — INT and DECIMAL count as one numeric
  rule, and a column mixing them becomes float): INT `^[+-]?\d{1,15}$` without leading zero
  → int, format `0` (never a thousands separator: years and codes are ints
  too); DECIMAL `^[+-]?\d{1,15}\.\d{1,6}$` → float, format `0.` + the column's
  maximum decimals (≤ 4); PERCENT `^[+-]?\d+(\.\d+)?\s?%$` → value/100, format
  `0%` / `0.0%`…; DATE `^\d{4}-\d{2}-\d{2}$` → date `yyyy-mm-dd`; DATETIME
  `…[T ]\d{2}:\d{2}(:\d{2})?$` → datetime `yyyy-mm-dd hh:mm`. Everything else
  stays text through `neutralize_formula`.
- One named Table per sheet, `displayName = Table{n}` (Excel-legal, unique —
  never derived from model text), a grayscale built-in style with row stripes,
  autofilter (from the Table), `freeze_panes = "A2"`, header row bold / wrapped
  / centred, widths from content (8–60), long text wrapped, numbers
  right-aligned, dates centred. Workbook properties: title, created.
- Headers unique and non-empty (Excel refuses the file otherwise — measured);
  ragged rows padded.

### 8.4 PDF

- Stylesheet built from `typography.py` (sans-serif → bundled Nimbus Sans;
  CJK → bundled Droid Sans Fallback, verified on Linux); page from the setting;
  metadata title / subject / creation date.
- Title block; running header (title) and localized footer stamped after
  layout with `insert_text` on every page (verified).
- Two-pass layout (`pdf_layout.py`): headings and table rows carry ids; pass 1
  records the page of each; long documents get a TOC with **exact page
  numbers** (re-laid out until the heading pages are stable, ≤ 3 iterations,
  else a TOC without numbers — never a wrong one), numbered headings, PDF
  outline bookmarks (`set_toc`, cheap, also on short documents with headings)
  and TOC entries linked to their pages (`insert_link` from the recorded rects).
- Tables: caption, header row bold with a bottom rule and NO background (the
  MuPDF phantom rectangle — measured), even-row banding on `td` **only if the
  corpus test counting stray fills on continuation pages stays at zero**,
  rows never split across pages (Story keeps rows whole), header row repeated
  on continuation pages by re-layout in best effort (≤ 2 extra passes, fallback
  = no repetition).
- Quote → `blockquote`; callout → `div.callout` (fill + left rule; the same
  stray-fill oracle applies to a callout crossing a page); `numbered` → `<ol>`.

### 8.5 MD / TXT / CSV

md: subtitle as an italic line, date, `1.` lists, `>` quotes, callouts as a
blockquote with a bold lead, table captions as an italic line above. txt:
numbered items `1)`, quotes indented, callouts fenced with rules, markers
stripped. csv: unchanged.

## 9. The fit estimator (`fit.py`)

Calibrated 2026-09-08 against PowerPoint 16 on the 16:9 geometry, 54
combinations of size (14–28 pt) × bullets (1–8) × length (25–140 chars):

```
usable_width = frame_width − 2 × 7.2 pt (insets) − 27 pt (level-1 indent)
lines(bullet) = max(1, ceil(len(bullet) × 0.42 × size / usable_width))     # 0 errors / 54
height = Σ lines × size × 1.2 + n_bullets × size × 0.2                        # ×1.05 → 0 under-predictions
```

The 54 measurements are committed as fixtures; the estimator must never
under-predict any of them, and a monotonicity test guards the arithmetic.
Procedure: `choose_body_size(bullets, frame)` walks the sizes down to the floor;
`plan_slides(bullets, frame)` returns the chunks and their per-slide size;
`fit_title(title, frame)` returns size and line count. **Stated limit**: the
calibration is Calibri metrics; Carlito (LibreOffice) is metric-compatible,
other viewers substitute — the 14 pt floor and the 5 % margin cover the common
case, not every substitution. The Office measurement harness (§16.3) re-checks
the half-width comparison geometry.

## 10. Truncation honesty (cross-cutting)

`infrastructure/llm/output_truncation.py`:

```python
def is_output_truncated(message) -> bool:
    meta = getattr(message, "response_metadata", None) or {}
    return (
        meta.get("finish_reason") in ("length", "MAX_TOKENS")                       # OpenAI chat, DeepSeek, Perplexity, Google
        or meta.get("stop_reason") == "max_tokens"                                 # Anthropic
        or meta.get("done_reason") == "length"                                     # Ollama
        or (meta.get("status") == "incomplete"
            and (meta.get("incomplete_details") or {}).get("reason") == "max_output_tokens")   # OpenAI Responses
    )
```

Each shape was read in the installed langchain adapters; a fixture per shape and
negative cases (`stop`, `tool_calls`, `end_turn`, no metadata) pin the predicate.

- Evaluated on the raw `AIMessage` **before any rescue**, in `_buffered_invoke`
  (the `include_raw` bundle) and in `_structured_via_auto_tool` (its `ai_msg`),
  raising `StructuredOutputTruncatedError(StructuredOutputError)` carrying
  provider, schema and the truncated text head.
- `get_structured_output_with_retry` re-raises it without retrying: a
  truncation is deterministic.
- Counted on the existing structured-output failure metric with a `truncated`
  reason when that counter is labelled, otherwise logged as
  `structured_output_truncated` (provider, schema, node) — a new metric would
  need a Grafana panel (metric-coverage ratchet); the plan checks which.
- The document tool maps it to an explicit failure naming the budget ("the
  document exceeded the output budget of N tokens of the `document_generation`
  slot; ask for a shorter document or split it") — no card, no retry.
- **Blast radius, stated**: every structured caller now fails honestly where it
  used to receive a silently shortened object (or three paid retries). Every
  `except StructuredOutputError` site keeps handling it by inheritance; the plan
  lists those sites and asserts each still returns its documented failure.

## 11. Owner at the door

`_call_document_llm` gains `user_id` and forwards it to
`get_structured_output_with_retry`. The guard's blind spot (a call accepted as
"carrying the owner" by name) is recorded in ADR-275; tightening
`test_every_spend_site_is_bounded` to require the `user_id=` keyword on
`_BOUNDED_CALLERS` is listed as a follow-up audit item, not done here, because
other `TURN` modules may legitimately rely on the entrance.

## 12. Prompt

`prompts/v1/document_generation_prompt.txt` (same file, edited in place; the
`PromptName` literal is unchanged) gains:

- the vocabulary and WHEN to use each kind — `numbered` for ordered steps,
  `quote` for verbatim words, `callout` for a warning or a key takeaway,
  `caption` to name a table, `subtitle` for audience/purpose; slides:
  `section` to open a part of a deck with three or more parts, `comparison` for
  two options, `table` for numeric data; speaker notes carry the sentences;
- the budgets as placeholders with their consequence: `{max_bullets_per_slide}`,
  `{max_bullet_chars}` ("beyond this the slide is split"),
  `{toc_min_headings}` ("beyond this the renderer adds a numbered table of
  contents — never write your own, never number your headings"),
  `{length_budget_words}` ("the output is cut beyond this and the document
  fails");
- inline markup allowed: `**bold**` and `*italic*` only, no other markdown, no
  headings inside a paragraph;
- tabular form that lets columns be typed: plain digits, dot decimal, ISO
  dates, `%` suffix; unique non-empty headers.

The service renders the placeholders from settings and from the slot's
effective `max_tokens` (`get_llm_config_for_agent`). Tests: every enforced
budget appears as a placeholder and no hard-coded number stands for it; every
`{placeholder}` in the file is supplied (a full `format` raises nothing and
leaves no brace); every value of both `Literal`s appears in the prompt text
(drift guard between vocabulary and its publication).

## 13. Repairs, never refusals

| Situation | Repair |
|---|---|
| `level` outside 1..4 | clamped |
| empty block / bullet / slide bullets | dropped |
| markdown list or heading inside a paragraph | converted to the block it is |
| heading pre-numbered by the model in a numbered document | prefix stripped |
| ragged table rows | widened to the longest row (generated headers for the extra cells), blank rows dropped |
| empty or duplicate header | localized "Column {n}" / " (2)" suffix |
| missing headers with rows | generated headers |
| table without rows and headers | dropped |
| slide kind without its payload | effective kind (§6.1) |
| ≥ 3 comparison columns | folded into a table |
| text that does not fit at the floor size | split across continuation slides, sentence then word boundaries |
| more table rows than a slide holds | chunked slides with the header repeated |
| PDF TOC pages not stable after 3 passes | TOC without page numbers |
| PDF header repetition not stable | no repetition |
| Excel-illegal Table name | never used — names are generated |
| `=`, `+`, `-`, `@` cell starters | `neutralize_formula` (unchanged) |

What still fails, honestly: a content family that does not match the format
(`ValueError`, unchanged), a library failure, a truncated model output (§10).

## 14. Consumers and compatibility

- **Meeting minutes** (`meetings/delivery.py`): pass `RenderContext(language,
  structure="plain", generated_at=None)`; the minutes gain header, footer and
  table craft and keep their structure. `tests/unit/domains/meetings/test_delivery.py`
  must stay green (its oracles are text containment).
- `tabular_io/writer.py`: unaffected (`neutralize_formula` unchanged).
- Frontend: nothing (cards are native links, no preview).
- Registers: `generate_document` stays `artefact`; one LLM call per document;
  no new spend site; `LLM_SPEND_ROADS` unchanged.
- Quotas without a user key: the `llm` family is instance-borne; the instance
  ceiling is asked at the door (owner `None`), the account ceiling at the turn
  entrance and — after §11 — at the door too.
- Cost: prompt +≈ 300–400 tokens per call, schema +≈ 150, output +≈ 10 %;
  `CostProfile` in the manifest stays (2000 in / 8000 out) — plausible, and
  re-measured with tiktoken in the plan.

## 15. Out of scope (YAGNI)

Images and charts on slides; ODT/ODS; per-user themes or brand assets; a
document preview in the chat; nested bullet levels (a recursive model would
deepen the strict schema); Word TOC page numbers without F9; a settings UI for
the four new tunables (env only).

## 16. Test plan

### 16.1 Unit (mirroring the source tree, all in the fast gate)

- `schemas`: defaults; strict verdict unchanged (`_analyze_schema_strict_compatibility`);
  bounded-property set is empty; the model-facing descriptions are one line.
- `normalize`: the effective-kind table (§6.1) exhaustively; empties; markdown
  leakage; heading prefix stripping only when numbered; clamping.
- `inline`: bold/italic/code/link, nested `***x***`, orphan markers, escapes,
  CJK, empty.
- `fit`: the 54 PowerPoint measurements as fixtures (no under-prediction);
  monotonicity in size and length; floor; greedy split determinism; sentence
  split of a 3 000-char bullet; title sizing.
- `tables`: typing by unanimity (leading zeros, years, phones with `+`, mixed
  int/float, `%`, ISO dates, `=` starters, whitespace, empties); header
  sanitizing; ragged rows; Excel name legality (`^[A-Za-z_][A-Za-z0-9_.]*$`,
  never cell-reference-shaped); chunking.
- `renderer_docx`: round-trip through python-docx; only named styles used;
  TOC field present with entries == headings on a long document and absent on
  a short one and under `plain`; numbering XML bound to Heading 1–3; list
  restart XML per list; footer fields; `tblHeader`; caption; page size per
  setting; CJK font declared; core properties.
- `renderer_pptx`: **slide size 960 × 540 pt and width > height**; layout per
  effective kind; slide number on every slide but the cover; **no text frame
  above the estimator's budget** (the internal oracle, applied to every frame
  of every corpus deck); continuation naming and counts; comparison mapping;
  ≥ 3 columns → table; caps disabled; table chunks with header; notes.
- `renderer_xlsx`: typed cells and formats per rule; Table + autofilter +
  freeze; unique legal names; sanitized headers; padded rows; widths bounded.
- `renderer_pdf`: page count; header and footer on every page; TOC page
  numbers == the pages where headings are extracted; outline entries; links;
  **zero stray filled rectangle at the top of continuation pages** (the
  phantom oracle, table and callout); CJK glyphs extracted; page size; metadata.
- `renderers_text`: md/txt for every kind; csv unchanged.
- `service`: context built from user language/timezone; `user_id` forwarded;
  placeholders rendered from settings and the slot's `max_tokens`; truncation
  mapped; meetings-style call without context.
- `tools/document_generation`: the truncation branch message.
- `infrastructure/llm/output_truncation`: the five shapes and negatives;
  `_buffered_invoke` raises before rescue (a raw message with
  `finish_reason=length` and a closable JSON must NOT yield a shorter object);
  the auto-tool path; the retry wrapper does not retry; every
  `except StructuredOutputError` caller still returns its failure.
- `core/i18n_documents`: six languages, identical key sets, identical
  placeholders.
- `config`: defaults from constants; `.env.example` hygiene.
- `prompts`: §12 guards.
- `meetings/test_delivery`: unchanged and green.

### 16.2 Corpus (`tests/fixtures/document_corpus/*.json`)

Deterministic contents, parametrized in the unit tests (every one renders in
every applicable format and passes the structural oracles) and rendered by the
harness: short memo; long report with tables; a 12-column table; a deck using
every kind; a 25-slide dense deck; a zh-CN document; edge cases (single block,
headings only, empty bullets, title-only slides); a typed spreadsheet (dates,
codes, negatives, percentages, formulas); duplicate headers; a very long title
and very long bullets; a meeting-minutes-shaped document.

### 16.3 Harness

- `task documents:corpus:render` (all platforms): `render_corpus.py` writes
  every corpus document in every applicable format to
  `apps/api/data/document_corpus_out/` (git-ignored).
- `task documents:corpus:measure` (Windows, on demand, never a gate — the
  `mobile:probe` shape): `measure_office.ps1` opens every docx/pptx/xlsx with
  Word / PowerPoint / Excel through COM, exports PDFs, rasterizes pages, and
  reports: **0 text frames overflowing per PowerPoint**, TOC entries and list
  strings per Word, fields computed, workbooks opened without repair. Run at
  review; the numbers go into the ADR.

### 16.4 Gates

`task lint` (size, complexity, coupling, docs with `lint:docs:preview` for the
new files, hygiene, i18n), `task test:backend:unit:fast`,
`task test:backend:unit:coverage` (floor raised by ≥ 2 pts if the measurement
allows), `task ci:fast` before hand-over.

## 17. Documentation and release surfaces

- **ADR-274** — the craft belongs to the renderer, the meaning to the model
  (amends ADR-226).
- **ADR-275** — a truncated structured output is a refusal, never a rescue
  (amends ADR-220 and ADR-226; records the owner-at-the-door finding).
- `docs/technical/DOCUMENT_GENERATION.md` rewritten: craft per format, the
  vocabulary and its repairs, the published budgets, the harness, the stated
  limits (Word TOC without page numbers, PDF header repetition best effort,
  estimator calibration).
- `docs/INDEX.md`, `docs/architecture/ADR_INDEX.md`, the CLAUDE.md pointer
  (+ `task docs:sync-agents`), `.env.example` / `.env.prod.example`, the
  Taskfile tasks, `task release:sync-counts`.
- Plan: `docs/superpowers/plans/2026-09-08-document-craft.md`.

## 18. Lots and order

| Lot | Content | Gate |
|---|---|---|
| 0 | `output_truncation` + raise before rescue + no retry + tool mapping + `user_id` at the door + ADR-275 | unit |
| 1 | package split, context, typography, i18n labels, settings, normalize (existing kinds), inline, fit, tables, the craft of every renderer, corpus + harness, meetings call site | unit + corpus + Office measurement |
| 2 | vocabulary (§6) + effective kinds + renderers for the new kinds | unit + corpus |
| 3 | prompt + placeholders + drift tests + manifest cost re-measured + ADR-274 + technical doc + indexes | lint:docs + ci:fast |

Each lot is green before the next starts; the review runs the harness and
reports the measurements.
