# AI Document Generation

## How do I create a document?
Simply ask in the chat: "Export this as a CSV", "Write a PDF report about…", "Make a presentation about Alsace". A dedicated writer model produces the full content in your language, and the finished file appears as a downloadable card below the answer. It also chains naturally with research: "research the latest LLM models, then formalize the result in a CSV" produces a file grounded in the fresh results of the same request.

## Which formats are supported?
Seven formats: **CSV** and **Excel (xlsx)** for data tables, **Word (docx)** for structured reports, **PowerPoint (pptx)** for presentations (with speaker notes), **PDF** for print-ready documents, plus **Markdown** and **plain text**. LIA picks the requested format; if you just say "a spreadsheet" or "a report", it chooses the most natural one. Spreadsheets are Excel-ready: correct accents and no formula injection by construction.

## What does the finished file look like?
Each format is drawn with its own codes, not as plain text in a grey box. A **presentation** is 16:9, with a layout chosen per intent — a part opener, a two-column comparison, a native table — and a slide number on every slide. A **Word** file carries a table of contents, numbered headings, a running head and pagination, all computed by Word itself: they stay right when you add a paragraph. An **Excel** file has typed columns, a frozen header and a filterable Table. A **PDF** has a contents page with exact page numbers, plus bookmarks and links. Text is measured before it is placed: a crowded slide is shrunk, then split in two rather than clipped.

## How do I view or download a generated document?
Each document appears as a card below the assistant's answer, with its filename, its type and its size. Click the download icon to save it — PDFs open directly in a new browser tab instead, so you can read them before deciding to keep them. The card survives a page reload: it stays in the conversation history, and says when the file is kept or no longer exists.

## How long does a document stay available, and what does it cost?
Generated files are temporary by default: each card shows its exact expiry deadline, and a warning appears when it gets close — keep the file from Settings › Preferences › My generated files (never deleted automatically, within your account's limit), or download it. The cost is the writer model's usage, counted like the rest of your AI usage within your account's limits. A technical rate limit per person, set by the administrator, additionally protects against runaway loops; normal use never hits it.

## Who can turn document generation off?

The administrator, in two places:
• **Settings › Administration › Platform capabilities** › **Document generation** — immediate, no redeploy. The document tool leaves what LIA can use, in both execution modes, and refuses a request that still reaches it
• the server configuration (`DOCUMENT_GENERATION_ENABLED=false` in the instance's environment file) — off there, the capability shows as unavailable and the switch above cannot turn it back on

There is no per-user switch: when the instance offers document generation, every user has it.

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
