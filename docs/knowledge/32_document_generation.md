# AI Document Generation

## How do I create a document?
Simply ask in the chat: "Export this as a CSV", "Write a PDF report about…", "Make a presentation about Alsace". A dedicated writer model produces the full content in your language, and the finished file appears as a downloadable card below the answer. It also chains naturally with research: "research the latest LLM models, then formalize the result in a CSV" produces a file grounded in the fresh results of the same request.

## Which formats are supported?
Seven formats: **CSV** and **Excel (xlsx)** for data tables, **Word (docx)** for structured reports, **PowerPoint (pptx)** for presentations (with speaker notes), **PDF** for print-ready documents, plus **Markdown** and **plain text**. LIA picks the requested format; if you just say "a spreadsheet" or "a report", it chooses the most natural one. Spreadsheets are Excel-ready: correct accents and no formula injection by construction.

## What does the finished file look like?
Each format is drawn with its own codes, not as plain text in a grey box. A **presentation** is 16:9, with a layout chosen per intent — a part opener, a two-column comparison, a native table — and a slide number on every slide. A **Word** file carries a table of contents, numbered headings, a running head and pagination, all computed by Word itself: they stay right when you add a paragraph. An **Excel** file has typed columns, a frozen header and a filterable Table. A **PDF** has a contents page with exact page numbers, plus bookmarks and links. Text is measured before it is placed: a crowded slide is shrunk, then split in two rather than clipped.

## How do I view or download a generated document?
Each document appears as a card below the assistant's answer, with its filename, its type and its size. Click the download icon to save it — PDFs open directly in a new browser tab instead, so you can read them before deciding to keep them. The card survives a page reload: it stays in the conversation history until the file expires.

## How long does a document stay available, and what does it cost?
Generated files are temporary by design: each card shows its exact expiry deadline, and a warning appears when it gets close — download the file to keep it. The cost is the writer model's usage, counted like the rest of your AI usage within your account's limits. A technical rate limit (by default 10 generations per 5 minutes per user, administrator-tunable via DOCUMENT_GENERATION_RATE_LIMIT_CALLS and DOCUMENT_GENERATION_RATE_LIMIT_WINDOW) additionally protects against runaway loops; normal use never hits it.

## Who can turn document generation off?
The administrator can disable the capability instance-wide via the platform capabilities panel (or the DOCUMENT_GENERATION_ENABLED environment variable), instantly and without redeploying — the tool then disappears from what the assistant can even propose. There is no per-user switch: when the instance offers document generation, every user has it.

## Which model writes the documents?
A dedicated LLM slot named "Document Generation" in the administrator's LLM Configuration (default: gpt-4.1). The administrator can point it at any configured chat model; its maximum output length bounds the largest producible document. If the model is cut at that budget mid-write, the generation FAILS and names the budget so you can ask for a shorter document or split it in two — it is never closed up and delivered as a complete one, which is what used to happen and is impossible to notice from the file itself. The content is then rendered locally into the exact file format, with no third-party document service involved.
