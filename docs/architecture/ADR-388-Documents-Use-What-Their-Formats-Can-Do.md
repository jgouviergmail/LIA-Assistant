# ADR-388 — Documents use what their formats can do

**Status**: Accepted, 2026-11-13.
**Date**: 2026-11-13

**Amends**:
[ADR-274](ADR-274-Document-Craft-Renderer-Owned-Model-Semantic.md) — its principle stands (the
model says what a thing IS, the renderer draws it); its « greyscale only » holds for a document
with no tone and is lifted for one the writer gives a tone, and its vocabulary grows.

**Builds on**: ADR-305 (image generation: the model that runs is the model that is priced),
ADR-184 (what is enforced is published), ADR-269 (a detail is repaired, never refused),
ADR-272 (every token the platform pays answers to both ceilings), ADR-221 amendment 2026-11-05
(a call's time is its slot's), ADR-085 (boot-time completeness).

## Context

The owner's request (2026-11-13): generated documents of professional quality on their FORM —
spreadsheets with formulas, references, sorts, filters and charts; presentations with
backgrounds, motion, pictograms and pictures LIA draws; text documents with advanced layouts;
complete, correct content and no layout error.

**Measured before any code.** A workbook carried typed columns and a filterable Table, but no
formula: the prompt forbade them, and openpyxl caches no formula value — a reader that does not
recalculate (a preview pane, a phone, the chat's excerpt) saw `None`. A deck had four layouts,
no chart, no picture, and the Office 2007 theme whose blue accent coloured anything native. Word
and PDF had no figure, no cover, and every link flattened to « text (url) ». ADR-274 §9 kept
everything grey.

**What had to hold.** Nothing overflows, whatever is added. Every number comes from the
document. A formula is right, recomputes, and its value reads everywhere. A picture costs per
unit: consent, the person's quality, ceilings, every euro traced. A partial failure is said, never
fatal. No brand identity. Everything stays editable. Accessible: alternative text, contrast,
nothing said by colour alone. Six languages, CJK included. Office, LibreOffice, Google, Apple.
Meeting minutes, rendered by the same engine, unchanged.

## Decision

1. **The principle stands; the vocabulary grows.** The writer says what a thing IS — a column
   that is an amount in a currency, a percent, a year, a code; a computed column; a chart's
   INTENT (compare, trend, share, relation); a deck's delivery (presented or read); key figures;
   a quote; a pictogram; a picture; the sources the text cites. Every closed list is published
   in the schema (`enum`) and REPAIRED at normalization, never refused: one unknown word would
   cost the whole document, three paid times (ADR-269).
2. **One grammar computes** (`formulas.py`, `computation.py`). A computed column's expression is
   read twice: as Excel text and as an exact value. It has the arithmetic, `ROUND`, `ABS`, `MIN`,
   `MAX`, a whole column's `SUM` and `AVERAGE`, `RUNNING_SUM`, `PREVIOUS`, and `IF` choosing
   between two numbers on a condition — two numbers compared, or a text column equal or not to a
   quoted text, joined by `AND`, `OR`, `NOT`. Where Excel is not arithmetic, its reading is
   mirrored so the cached value is the recalculated one: `IF` computes only the value it chooses
   and returns a reference when that value is one; `MIN` and `MAX` skip a reference holding no
   number; two numbers compare on 15 significant digits, a text without case; a computed cell with
   no value is an empty text in the workbook, so whatever reads it in arithmetic is wrapped in
   `IFERROR` too, and no comparison reads it — or the row above, the header on the first row —
   bare. A column never reads itself: in its own formula its name is the input of that name
   (`Rent` computed as `{Rent}`), or the formula is refused. And no value is ever computed from a
   computation that failed: a column whose formula is dropped keeps what the writer wrote in it,
   or goes when nothing was written, and every formula reading it fails in turn; only the members
   of a cycle lose their formula, never the columns that merely read it. A workbook carries live
   formulas WITH their cached values (XlsxWriter writes; openpyxl only reads), a totals row whose
   totals are given,
   assumptions as defined names, a summary by group in `SUMIFS`, a drop-down for a closed list,
   a colour scale for a measure with a good direction. Every other format shows the computed
   values in the reader's conventions. The model never computes.
   **A workbook's key figures** — the quantities it exists to answer, each drawn from several
   sheets or rows (a year's income, the share left after expenses) — are a list of their own
   (`workbook_figures.py`): a label and a formula of the same grammar with no row, reading the
   inputs and the other figures by name and a sheet's whole column as `SUM({Sheet/Column})` or
   `AVERAGE({Sheet/Column})`. Each is computed once, after the figures it reads, and written
   live on a sheet of its own between the assumptions and the data, as a defined name with its
   cached value (`renderers/xlsx_figures.py`); an input wins over a figure of its name, as in a
   column's formula. A figure with no value is an empty text, held to a computed cell's rules:
   `MIN` and `MAX` skip it — a defined name is a reference — and no comparison reads it bare.
   What cannot be computed goes, with every figure reading it: a row read, a text column, an
   unknown name, a cycle. The bound is published and held
   (`DOCUMENT_GENERATION_WORKBOOK_FIGURES_MAX`).
3. **A chart is an intent; its form is the renderer's** (`charts.py`): the form the data can
   bear, a form the person named kept when the data bears it — a pie of fifteen slices cannot
   be drawn. Each format uses its native mechanism: Excel reads the sheet's cells (a gap is a
   gap, never a zero), PowerPoint embeds an editable chart, the PDF draws vectors whose words
   stay text, Word holds a picture with its words as alternative text, Markdown and text give the
   table of the values. One palette, validated for contrast on paper and for colour-blind readers.
4. **A palette by tone** (`typography.PALETTES`): `sober`, `institutional`, `warm`, `technical`.
   The accent marks structure only — titles, large headings, rules, a part opener, a figure's
   value — never small text; a link takes the accent only where it holds 4.5:1, and is
   underlined either way. The theme of a Word or PowerPoint file is recoloured to it. **No tone
   keeps the grey of before**, so meeting minutes are unchanged.
5. **The person decides** (Settings › Documents, `users.document_illustrations` and
   `users.document_animations`, read through ONE door `core/document_preferences.py`):
   illustrations `auto` (the writer judges), `on_request`, `never`; a deck's animations
   `presented` (only a deck the writer declares presented), `always`, `never`.
6. **Presentations** gain key figures as tiles (balanced rows, one type size per row), quotes,
   an agenda the renderer adds from several parts (the writer never writes one), pictograms from
   a closed Lucide set (ISC, its geometry vendored and drawn as PNG, marked decorative), native
   charts, and pictures in four frames (cover, part opener, beside points, alone). A presented
   deck moves soberly: fade transitions and points revealed one at a time, written as
   PresentationML. Whatever cannot fit falls back to bullets, which split.
7. **Illustrations are image generations** (ADR-305), and nothing else decides they exist: the
   person's image opt-in and their document choice, a format that places pictures (pptx, docx,
   pdf), ONE budget (`pictures.illustration_budget`, `DOCUMENT_ILLUSTRATIONS_MAX`) published in
   the prompt's tail and enforced by normalization (the cover first), both spend ceilings asked
   before the first picture. The writer gives each a subject in English and alternative text in
   the document's language, and the document ONE style. They are drawn on the image slot at the
   person's quality and size tier, the frame deciding the proportions, a few at a time, all
   within one call's time of that slot (the tool's step declares both slots), each billed to the
   turn through the call the image tool shares (`image_generation/billed_call.py`). A picture
   that fails is left out and said — by facts, never by an error's words (ADR-303). No prompt
   enhancement: the writer already wrote the prompt.
8. **Reports** gain a cover page (a long document: Word's « different first page », an
   unstamped PDF page), a band of key figures, pictures as figures numbered with the charts, the
   sources they cite as [n] — a source keeps its place, which is its number in the text, and
   only a web address with a host becomes a link — every printed address clickable (Word
   hyperlinks, PDF link annotations, PowerPoint run links; on paper the address stays printed),
   and landscape pages in Word for a table of eight columns or more, the heading that announces
   it turning with it. Markdown and text list the figures and the sources and hold no picture:
   their writer is asked for none.
9. **Each family reads its own rules**, and the illustration rules — which depend on the
   person — stand in the prompt's dynamic tail, so the cached head stays shared.

## Measurements

Rendering, in the tests: every corpus document reopens in every applicable format, nothing
overflows a slide, normalization is idempotent over the corpus, and the lot's guards were proven
by mutants (every one killed).

What the PDF engine does, measured on the pinned PyMuPDF while building: an SVG `<img>` comes
out as a bitmap at about 96 dpi (a figure is therefore an empty room the finish draws into as
vectors); the Story never moves an image to the next page, it squeezes it (250 pt laid out as
78 pt); a CSS page break before a picture cycled forever; links are coloured by its own sheet
under `a[href]`, which a plain `a` rule loses to; it reads one value of `border-spacing` for
both axes; it writes no link annotation of its own, reporting one rectangle per word of an
`<a>`; it breaks a long address by itself. Word joins two adjacent tables into one: a band's
rows stand apart by a one-point paragraph.

The writer, on real models (`task documents:writer:measure`, 2026-11-13): eight scenarios — a
deck to present, a deck to read, a deck whose request asks no picture, a report citing given
sources, a brief with none, a long annual report, a budget workbook, a short note — on the proof
account, five configurations of two providers (a fast model with and without reasoning, three
models of the other provider), 133 runs, 3.85 USD and 0.27 USD spent:

- **The published rules held from the start**: 122 to 130 of 126 to 132 verdicts per
  configuration. No address was ever invented; every report given sources listed and cited
  them, a brief given none listed none; no picture past the budget, none where the request asked
  none; every presented deck declared so; every long document recognised as one.
- **Two rules were calibrated on the measurement.** The fast configuration without reasoning
  wrote formulas the grammar never had — `IF`, comparisons, text — and 28 of its 66 survived; the
  prompt now says what the grammar has NOT and what to do instead (a conditional value is written
  in its cells): 23 of 26. A key figure was sometimes a number the writer computed (14 people
  joined and 3 left: « +11 »; a sum of the expenses) — in 9 runs of 96; the rule now forbids a
  computed number too: 1 run in 37 after.
- **A document costs** 0.0015 to 0.18 USD and takes 10 to 109 s by configuration, the
  reasoning ones the slowest; output from about 700 to 9 000 tokens.
- **What no prompt repairs was repaired in the shared door** (ADR-100 amendment 2026-11-13).
  Two reasoning configurations wrote a workbook's `sheets` as JSON TEXT: one stopped the text
  between two values and wrote the rest of the sheet beside it — 4 of 9 workbooks lost, each
  refused answer paid again up to three times; the other closed the text once too often, or broke
  it with a stray character — 7 refusals in 8 workbooks, one lost. A fast configuration without
  reasoning closed a long report's arguments once too often (one report lost in 24). After, every
  document of the same scenarios came in one call: 6 workbooks of 6 and 8 of 8 (three of them read
  back), 8 long reports of 8 — and no repair triggered on four decks and reports that needed none.
- **The grammar grew where the writers reached**: `IF`, comparisons and text — what the fast
  configuration without reasoning wrote and the grammar refused — and a running total. After, the
  reasoning configurations kept their formulas: 24 of 24, 25 of 25, 77 of 77, and 82 of 87. The
  fast one without reasoning kept 77 of 117; a diagnosis of five more of its workbooks named the
  losses — of 72 formulas, 41 dropped: 6 its own (a choice among a summary's line labels nested
  past the bound, a name from another sheet) and 35 one naming habit: a column named like the
  input it shows (`Rent` reading `{Rent}`), read as the column itself, dropped as a cycle with
  every formula reading it — 3 workbooks of 5 delivered with empty computed columns. Read as the
  input since (decision 2): 109 of 123 kept on eight more workbooks, the 14 others the writer's
  own nested choices past the bound (7) and the formulas reading them (7), dropped with them.
- **Key figures** (2026-11-14, the budget workbook, the prompt as shipped): declared in every
  workbook of the fast configuration without reasoning — 104 kept in 10, from 6 to 18 each — and
  in 4 of 4 of one reasoning configuration's, 2 of 2 of the other's, whose formulas were all kept
  (59 of 59, 15 of 15) with their charts. The summaries of empty cells are gone: the fast
  configuration's workbooks delivered complete went from 6 in 10 to 7 in 10, the columns still
  empty a quarterly view and a scenario table. That configuration still loses formulas in every
  workbook — 259 of 313 kept — on references Excel reads and the grammar does not: a column
  formula reading a key figure by name (7) or another sheet's whole column (4), a key figure
  asking a column's `MIN`, `MAX` or `COUNT` (5); and on what nothing could read: another sheet's
  ROW named as a column (8), nested choices past the bound or broken (9). The decks, reports and
  note of the same pass kept every rule they kept before.
- **What no reader can show never fails the document** (cold review, 2026-11-14, probes on the
  rendered document): a compound rate written whole — `(1 + 6) ^ 40` — raised in every format,
  after the writer and the pictures were paid for, and so did a date computed outside the
  calendar; an input declared `code` was written as a TEXT, which Excel compares as larger than
  any number where the cached value read the number; a negative value at an exact half lost its
  sign (-0.005 read 0.01). Since: a result past what Excel holds (9.99E+307) is a row without
  value, a long number is written whole, a date no calendar holds is an empty cell, an input is a
  number or a date, ONE rounding decides a number and its sign, and a drop-down whose choice holds
  a quote is read from cells — written inline, the list is a formula Excel cannot read.

## What this decision leaves, and says so

- **Office's verdict** on what is written by hand — transitions and reveals, the recoloured
  theme, charts — is the owner's measurement (`task documents:corpus:measure`): Office refuses
  COM activation from the agent's session. The tests read every file back with the libraries
  that wrote it.
- A chart in Word is a picture: python-docx writes no chart part.
- A PDF carries no tagged structure; a picture's alternative text lives in Word.
- Out of scope: pivot tables and slicers (XlsxWriter writes neither; summaries by group stand
  in), SmartArt, a brand identity, OpenDocument formats, video, editing an existing document.
- The writer's honesty about numbers is MEASURED (figures found in the material), not enforced:
  a number the material does not give is the writer's, and the prompt forbids it.
- Excel's comparison on 15 significant digits is documented by its community, not specified by
  Microsoft; the corpus measurement in Office is what confirms a cached comparison.
- A column's formula is the same for every row of its column, and reads its own sheet and the
  inputs: a summary whose rows are different quantities, each drawn from another sheet, is out of
  its reach — it is a list of key figures (decision 2). Measured before they existed, with a
  prompt saying a column could not: 3 workbooks of 10 of the fast configuration without reasoning
  still wrote such a summary — its cells left empty, or a choice among its line labels nested past
  the bound (11 of its 12 refused formulas) — and none of the eight workbooks of two reasoning
  configurations did.
- A key figure reads a sheet's whole column, never a cell or a filtered part of it: a figure by
  category is a sheet's `summary`. Its whole-column functions are `SUM` and `AVERAGE` alone.
- A column's formula reads its own sheet and the inputs: not a key figure, not another sheet's
  column, though Excel reads both — that needs one dependency order for the whole workbook
  (figures, and every sheet's columns), which is not built. Measured above: 11 of the fast
  configuration's 33 refused formulas.
- A column the writer leaves empty WITHOUT a formula is data, read as zero by a formula — a
  template's columns, or a writer's omission: the renderer cannot tell them apart and computes
  what the workbook states, never filling it from an input of the same name (an empty
  « December bonus » would get the bonus every month). Measured: one budget of eight with its
  expense columns left empty, its totals at zero; the writer is now told that every column holds
  its values, and none of eighteen budgets since left a data column empty — the empty columns that
  remain are a summary's (above) and one left for the reader to fill.

## Consequences

- The tool's signature is unchanged; its message says what became of the pictures.
- A document may now cost images: priced, attributed to the turn, bounded by both ceilings and
  the instance budget, shown in the person's costs like any image.
- `DOCUMENT_ILLUSTRATIONS_MAX` joins the configuration (0 switches illustrations off); two
  columns join `users`; XlsxWriter is a declared dependency, imported on first use.
- The documents' measurement has two instruments: Office's verdict on the corpus, and the
  writer's paid measurement on real models.

## References

- `apps/api/src/domains/document_generation/` — `schemas.py`, `normalize.py`, `formulas.py`,
  `computation.py`, `workbook_figures.py`, `charts.py`, `typography.py`, `pictures.py`,
  `illustrations.py`, `renderers/`.
- `apps/api/src/domains/image_generation/billed_call.py` — the call both image paths share.
- `apps/api/src/core/document_preferences.py` — the person's choices.
- `apps/web/src/components/settings/DocumentSettings.tsx` — Settings › Documents.
- `apps/api/scripts/document_generation/measure_writer.py`,
  `writer_scenarios.json` — the writer's measurement.
- [DOCUMENT_GENERATION.md](../technical/DOCUMENT_GENERATION.md),
  [IMAGE_GENERATION.md](../technical/IMAGE_GENERATION.md).
