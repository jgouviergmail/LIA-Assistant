# Knowledge Spaces (RAG)

## What are Knowledge Spaces?
Knowledge Spaces (RAG — Retrieval-Augmented Generation) allow you to upload your own documents to create personal knowledge bases. When you ask a question, LIA automatically searches these documents and enriches its responses with relevant content.**Key features:**
- Upload 15+ formats: PDF, TXT, MD, DOCX, PPTX, XLSX, CSV, RTF, HTML, ODT, ODS, ODP, EPUB, JSON, XML
- Automatic chunking and indexing via Gemini embeddings
- Hybrid search (semantic + BM25 keyword) for optimal relevance
- Source citations in responses

## What file formats are supported?
Knowledge Spaces accept **15+ formats**:
- **PDF** — text extraction via PyMuPDF
- **TXT** — plain text files
- **Markdown (.md)** — documentation and notes
- **DOCX** — Microsoft Word documents
- **PPTX** — PowerPoint presentations
- **XLSX** — Excel spreadsheets
- **CSV** — tabular data
- **RTF** — Rich Text Format
- **HTML** — web pages
- **ODT / ODS / ODP** — LibreOffice documents
- **EPUB** — e-books
- **JSON** — structured data
- **XML** — structured markup

**Limits:** maximum 20 MB per file, up to 50 documents per space, and 10 spaces per user.

## How does document processing work?
When you upload a document, LIA processes it in the background:

- **Text extraction** — content is extracted based on file type
- **Chunking** — text is split into overlapping segments (1000 characters with 200 overlap)
- **Embedding** — each chunk is converted to a vector using OpenAI's embedding model
- **Indexing** — vectors are stored in PostgreSQL (pgvector) for fast similarity search
The document status changes from *processing* to *ready* when complete. If an error occurs, the status shows *error* with details.

## How do I activate or deactivate a space?
Each space has an **activation toggle**. When a space is active, its documents are included in RAG searches during conversations.**Tips:**
- Only activate spaces relevant to your current work to improve relevance
- An indicator in the chat header shows how many spaces are active
- Click the indicator to quickly manage your spaces
- Deactivating a space does not delete any data — you can reactivate it anytime

## How does hybrid search work?
LIA combines two signals, but they do not carry the same weight.
- **Semantic search decides** — multilingual vector embeddings compare the *meaning* of your question with each passage (cosine similarity). That score alone determines whether an excerpt is relevant.
- **BM25 breaks ties** — exact word matching adds a bounded bonus that can lift a literal occurrence above a near-tie. It can neither admit nor evict an excerpt.

This separation came out of a fix: blending both signals in comparable shares discarded one correct answer in three as soon as the question's language drifted from the documents'.The relevance threshold was recalibrated across the **six languages** on real corpora. Space-less scripts (Chinese, Japanese, Korean) are split into character bigrams, without which a whole sentence would count as a single word.**Quality controls:** semantic relevance threshold, token budget limit (2000 tokens max), and configurable number of excerpts per query.

## How much does RAG cost?
RAG uses OpenAI embeddings, which have a small cost:
- **Indexing** (upload) — one-time cost per document, using gemini-embedding-001
- **Search** (each query) — embedding of your question (~few tokens per query)

Costs are **fully tracked** and visible in the assistant message cost breakdown and your usage dashboard. The RAG embedding cost appears under the gemini-embedding-001 model.**Tip:** For a typical 10-page PDF, indexing costs less than $0.001.

## How does Google Drive sync work?
You can link Google Drive folders to your knowledge spaces. Click **'Link Folder'**, browse your Drive, and select a folder. LIA lists the supported files, downloads them, and processes them through the same indexing pipeline.Use **'Sync Now'** to update — LIA detects new, modified, and deleted files automatically.**Key details:**
- Supports Google Docs, Sheets, and Slides via API export
- Per-file error isolation — one failed file does not block others
- Feature flag: RAG_SPACES_DRIVE_SYNC_ENABLED

## Can I ask the assistant about its own features?
Yes! LIA has a **built-in knowledge base** that lets it answer questions about itself directly in conversation:

**🧠 How it works:**
• LIA automatically detects when you ask about the app ("*What can you do?*", "*How do I connect my calendar?*")
• It searches its FAQ knowledge base (200+ Q&A across 24 sections) using the same hybrid search as user spaces
• An **App Identity Prompt** describing all capabilities is injected into the response

**⚡ Zero overhead:**
This only activates when you ask about the app. Normal queries (emails, calendar, etc.) are not affected at all.

**🔧 Admin features:**
Administrators can manage system knowledge spaces in **Settings > Administration > RAG Spaces**:
• View staleness status (content hash comparison)
• Trigger a manual rebuild — the button reports which of three things happened: rebuilt, already up to date, or a rebuild already in progress
• The corpus is checked at every start against both the source files and what is actually stored, so a corpus that has drifted is repaired rather than served
• If a rebuild cannot run, the previous version keeps answering and the failure is reported instead of passing unnoticed

## Can LIA search my documents on its own? (v1.25.13)
Yes. Your document spaces are now an **active domain**: beyond the automatic context injection, the planner can decide to search them — with derived queries, several passes if needed, and combinations with other sources: « compare the PDF quote with what Paul sent by email » chains a document search and an email search.

The « Documents » briefing card also shows your latest modified Drive files — one click to summarize in chat, or open directly in Drive.

## Can I download, move or delete several documents?
Yes. Every document in a space offers **Download** — the original file, under its original name — and ticks to act on several at once. A selection can be **downloaded as one zip archive**, **moved to another space** or **deleted** in one go.

A move takes everything with it: the row, the index the search reads and the file itself — after which the document answers from its new space, and only from there. What stays put is what LIA maintains for you: documents synced from a Google Drive folder and meeting minutes, which belong to their source.

Every batch tells you what it did and what it left aside, with the reason — target space full, document still being indexed, document managed elsewhere. And nothing moves during a general reindex: LIA would rather refuse cleanly than move a document the engine is re-reading.
