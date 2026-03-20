# Knowledge Spaces (RAG)

## What are Knowledge Spaces?
Knowledge Spaces (RAG — Retrieval-Augmented Generation) allow you to upload your own documents to create personal knowledge bases. When you ask a question, LIA automatically searches these documents and enriches its responses with relevant content.**Key features:**Upload 15+ formats: PDF, TXT, MD, DOCX, PPTX, XLSX, CSV, RTF, HTML, ODT, ODS, ODP, EPUB, JSON, XMLAutomatic chunking and indexing via OpenAI embeddingsHybrid search (semantic + BM25 keyword) for optimal relevanceSource citations in responses

## What file formats are supported?
Knowledge Spaces accept **15+ formats**:**PDF** — text extraction via PyMuPDF**TXT** — plain text files**Markdown (.md)** — documentation and notes**DOCX** — Microsoft Word documents**PPTX** — PowerPoint presentations**XLSX** — Excel spreadsheets**CSV** — tabular data**RTF** — Rich Text Format**HTML** — web pages**ODT / ODS / ODP** — LibreOffice documents**EPUB** — e-books**JSON** — structured data**XML** — structured markup**Limits:** maximum 20 MB per file, up to 50 documents per space, and 10 spaces per user.

## How does document processing work?
When you upload a document, LIA processes it in the background:**Text extraction** — content is extracted based on file type**Chunking** — text is split into overlapping segments (1000 characters with 200 overlap)**Embedding** — each chunk is converted to a vector using OpenAI's embedding model**Indexing** — vectors are stored in PostgreSQL (pgvector) for fast similarity searchThe document status changes from *processing* to *ready* when complete. If an error occurs, the status shows *error* with details.

## How do I activate or deactivate a space?
Each space has an **activation toggle**. When a space is active, its documents are included in RAG searches during conversations.**Tips:**Only activate spaces relevant to your current work to improve relevanceAn indicator in the chat header shows how many spaces are activeClick the indicator to quickly manage your spacesDeactivating a space does not delete any data — you can reactivate it anytime

## How does hybrid search work?
LIA uses a **hybrid search** combining two complementary techniques:**Semantic search** — finds content with similar meaning using vector embeddings (cosine similarity)**BM25 keyword search** — finds content with matching keywords (exact term matching)Results are merged using a weighted fusion formula. This ensures both conceptually relevant and keyword-accurate results are surfaced.**Quality controls:** minimum relevance score threshold, token budget limit (2000 tokens max), and configurable number of chunks per query.

## How much does RAG cost?
RAG uses OpenAI embeddings, which have a small cost:**Indexing** (upload) — one-time cost per document, using text-embedding-3-small ($0.02/million tokens)**Search** (each query) — embedding of your question (~few tokens per query)Costs are **fully tracked** and visible in the assistant message cost breakdown and your usage dashboard. The RAG embedding cost appears under the text-embedding-3-small model.**Tip:** For a typical 10-page PDF, indexing costs less than $0.001.

## How does Google Drive sync work?
You can link Google Drive folders to your knowledge spaces. Click **'Link Folder'**, browse your Drive, and select a folder. LIA lists the supported files, downloads them, and processes them through the same indexing pipeline.Use **'Sync Now'** to update — LIA detects new, modified, and deleted files automatically.**Key details:**Supports Google Docs, Sheets, and Slides via API exportPer-file error isolation — one failed file does not block othersFeature flag: RAG_SPACES_DRIVE_SYNC_ENABLED

## Can I ask the assistant about its own features?
Yes! LIA has a **built-in knowledge base** that lets it answer questions about itself directly in conversation.

**🧠 How it works:**
• LIA automatically detects when you ask about the app ("*What can you do?*", "*How do I connect my calendar?*")
• It searches its FAQ knowledge base (119+ Q&A across 17 sections) using the same hybrid search as user spaces
• An **App Identity Prompt** describing all capabilities is injected into the response

**⚡ Zero overhead:**
This only activates when you ask about the app — normal conversations are not affected. The system knowledge spaces are lazy-loaded (only initialized on first app-help query) and shared across all users.

**📚 System knowledge spaces:**
In addition to your personal knowledge spaces, LIA includes built-in system knowledge spaces managed by the platform. These contain curated FAQ content and are not editable by users. They are marked with a special badge in the admin interface and can be reindexed when the FAQ is updated.
