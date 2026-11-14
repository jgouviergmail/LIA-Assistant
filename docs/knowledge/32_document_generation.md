# AI Document Generation

## How do I create a document?
Simply ask in the chat: "Export this as a CSV", "Write a PDF report about…", "Make a presentation about Alsace". A dedicated writer model produces the full content in your language, and the finished file appears as a downloadable card below the answer. It also chains naturally with research: "research the latest LLM models, then formalize the result in a CSV" produces a file grounded in the fresh results of the same request.

## Which formats are supported?
Seven formats: **CSV** and **Excel (xlsx)** for data tables, **Word (docx)** for structured reports, **PowerPoint (pptx)** for presentations (with speaker notes), **PDF** for print-ready documents, plus **Markdown** and **plain text**. LIA picks the requested format; if you just say "a spreadsheet" or "a report", it chooses the most natural one. Spreadsheets are Excel-ready: correct accents and no formula injection by construction.

## What does the finished file look like?
Each format is drawn with its own codes, in a palette matched to the document's tone (sober, institutional, warm or technical; without a tone it stays grey).
• A **presentation** is 16:9, with a layout chosen per intent — a part opener, a two-column comparison, a native table, an editable chart, key figures as tiles, a quote — a slide number on every slide, an agenda when the deck has several parts, and pictograms from a fixed set. A deck you will present gets sober transitions and points revealed one by one.
• A **Word** file opens on a cover page when it is long, then a table of contents, numbered headings, a running head and pagination, all computed by Word itself; its key figures form a band of tiles, its charts and pictures are numbered figures, a very wide table gets landscape pages, and the sources it cites close it, numbered, with links you can open.
• An **Excel** file has typed columns (an amount with its currency, a percentage, a date), a frozen header and a filterable Table, real formulas — conditions and running totals included — whose values are already computed, a totals row, summaries by group, a sheet of key figures drawn from every sheet, drop-down lists and native charts that read the cells.
• A **PDF** opens on a cover when it is long, with a contents page giving exact page numbers, bookmarks, crisp charts and clickable links.
Text is measured before it is placed: a crowded slide is shrunk, then split in two rather than clipped. LIA never computes a value itself in a document: it declares a formula, and the file computes it.

## Can my documents be illustrated or animated?
Yes, in **Settings › Documents**. Two choices apply to every document LIA creates for you:
• **Illustrations**: *LIA judges* (the default: a picture only where it serves the document — its cover, or the opening of a part of a presentation or a report — never in a short note), *On request* (only when your request asks for images) or *Never*. Illustrations exist in PowerPoint, Word and PDF documents; Markdown, text and spreadsheets have none.
• **Animations** of PowerPoint presentations: *Presented decks* (the default: transitions and points revealed one at a time only for a deck you will present on screen; a deck meant to be read stays still), *Always* or *Never*.
An illustration is an image generation: it needs image generation turned on for your account, it is drawn with your image quality and size, and it is counted in your costs like any other image. The administrator caps how many pictures one document may carry. If an illustration fails, the document is still delivered, without it, and LIA says so.

## Can a document cite its sources?
Yes. When the material LIA works from names where its facts come from — web results, articles, reports — a Word, PDF or Markdown document cites them in the text as [1], [2]… and lists them at the end, numbered, each with a link that opens. An address is copied from the material, never invented; without a source in the material, the document lists none.

## How do I view or download a generated document?
Each document appears as a card below the assistant's answer, with its filename, its type and its size. Click the download icon to save it — PDFs open directly in a new browser tab instead, so you can read them before deciding to keep them. The card survives a page reload: it stays in the conversation history, and says when the file is kept or no longer exists.

## How long does a document stay available, and what does it cost?
Generated files are temporary by default: each card shows its exact expiry deadline, and a warning appears when it gets close — keep the file from Settings › Preferences › My generated files (never deleted automatically, within your account's limit), or download it. The cost is the writer model's usage, plus one image generation per illustration when there are any, counted like the rest of your AI usage within your account's limits. A technical rate limit per person, set by the administrator, additionally protects against runaway loops; normal use never hits it.

## Who can turn document generation off?

The administrator, in two places:
• **Settings › Administration › Platform capabilities** › **Document generation** — immediate, no redeploy. The document tool leaves what LIA can use, in both execution modes, and refuses a request that still reaches it
• the server configuration (`DOCUMENT_GENERATION_ENABLED=false` in the instance's environment file) — off there, the capability shows as unavailable and the switch above cannot turn it back on

There is no per-user switch for the tool itself: when the instance offers document generation, every user has it. What each person decides is how their documents are illustrated and animated (**Settings › Documents**).

## Which model writes the documents?

A model your administrator picks for that job alone: the **Document Generation** entry of the LLM configuration, separate from the chat model. It must be able to return structured content, and its maximum answer length bounds the largest document it can write.

**✂️ If the model is cut short:** the generation **fails and says so**, naming the limit, so you can ask for a shorter document or split it in two. A cut document is never closed up and delivered as if it were complete.

**🏠 Built on your server:** the model writes the content; LIA then builds the real file — Word, Excel, PowerPoint, PDF… — on your LIA server, with no third-party document service. The cost is that model's usage, counted like the rest of your AI usage.

## Do my documents stay accessible if attachments are switched off?
Yes. Uploading a file and consulting your own files are two different things,
and only the first depends on the attachments setting. A report LIA wrote
opens, downloads and deletes from **Settings › Preferences › My generated files** even on an
instance where uploads are off, and its retention deadline is still applied.
The public demonstrator is such an instance: it accepts no upload, yet
document generation is on there.
