# Document Generation Agent — Design Specification

- **Date**: 2026-08-17
- **Status**: Approved design, pre-implementation
- **ADR**: ADR-226 (to be written in Lot 0)
- **Pattern mirrored**: `image_generation` domain (virtual agent manifest + tools + Attachment TTL storage + SSE card delivery)

## 1. Goal

Give the assistant a new capability: creating downloadable documents (csv, xlsx, docx, pptx, pdf, md, txt) on user request, in both execution modes (pipeline and ReAct). Examples:

- "Research the latest LLM models and formalize the result in a CSV" → web research steps feed a document step.
- "Generate a detailed presentation about Alsace" → a PPTX is produced directly.

Documents appear as cards below the assistant message (like generated images), can be downloaded (PDF also viewable inline), and are purged automatically after the attachments TTL.

## 2. Validated foundations (all verified in code or by executed probes)

| Fact | Evidence |
|---|---|
| Attachment model supports documents, TTL, ownership | `src/domains/attachments/models.py` (`AttachmentContentType.DOCUMENT`, `expires_at` indexed) |
| Cleanup scheduler purges expired attachments every 6 h | `src/infrastructure/startup/schedulers.py` (attachment_cleanup job) |
| Serving endpoint downloads non-images with ownership check | `src/domains/attachments/router.py` (`content_disposition_type="attachment"`) |
| Virtual agent pattern (no LangGraph graph) | `image_generation_agent`: manifest + tools only, never in `startup/agents.py` |
| Card delivery live + after reload | `image_store.py` pending store → done chunk + `message_metadata` persistence (`agents/api/service.py`) |
| ReAct exposure is automatic via domain detection | `react_nodes.py` `ReactToolSelector().select(intelligence)` |
| Pipeline chaining research → document | `$steps` templating (`orchestration/step_references.py`) |
| All 5 binary formats writable with ZERO new dependency | Executed probe: openpyxl 3.1.5, python-docx, python-pptx 1.0.2, PyMuPDF 1.27.2 (incl. Story HTML→PDF), csv stdlib — all OK |
| openpyxl stores a leading `=` string as a FORMULA | Executed probe: `data_type == "f"` → formula-injection neutralization is MANDATORY |
| Starlette `FileResponse` encodes non-ASCII filenames per RFC 5987 | Executed probe: `filename*=utf-8''r%C3%A9sum%C3%A9...` |
| `utf-8-sig` BOM produces Excel-compatible CSV | Executed probe: leading `\xef\xbb\xbf` |
| User preference columns are enumerated in the GDPR data map | `src/domains/users/user_data_map.py` (`image_generation_enabled` → `_PREFERENCE`) |

## 3. Architecture decisions (approved)

1. **Content production — internal dedicated LLM** (mirror of `generate_image`): the tool calls a new LLM type `document_generation` (added to `LLM_TYPES_REGISTRY` + `LLM_DEFAULTS`, admin-overridable) that produces **structured content typed per format** (Pydantic schemas), then a **pure renderer** writes the file. Planner-supplied `source_data` (via `$steps` templating) is the raw material channel for research-then-formalize flows; in ReAct mode the model fills `source_data` inline.
2. **Formats v1**: csv, xlsx, docx, pptx, pdf, md, txt.
3. **PDF renderer**: PyMuPDF Story (HTML→paged PDF), zero new dependency, already shipped for RAG extraction (ARM64 prod proven).
4. **Visualization v1**: document card (type icon, meaningful filename, size, expiry deadline, download button); `application/pdf` served with `inline` disposition so it opens in the browser tab (applies to uploaded PDFs too — user's own files, ownership-checked; UX improvement, not a regression). Rich in-chat previews (CSV/XLSX table) deferred to v2.
5. **TTL**: reuse `attachments_ttl_hours` (single purge pipeline, deadline surfaced on the card exactly like image cards — N2 rule: unknown deadline → say nothing).
6. **Cost**: LLM tokens through the standard token-tracking (new llm type) — **no dedicated pricing table** (unlike images: there is no per-unit external API price here).
7. **HITL**: not required (non-destructive creation), like `generate_image`.

## 4. Backend design

### 4.1 New domain module `src/domains/document_generation/`

- `schemas.py` — per-format structured content models produced by the LLM:
  - `CsvContent` (headers + rows), `XlsxContent` (sheets → headers/rows, optional column widths), `DocxContent` (title + sections: heading/paragraph/bullets/table), `PptxContent` (slides: title + bullets + optional notes), `PdfContent` (same section tree as docx, rendered via HTML → Story), `MarkdownContent` / `TextContent` (plain body).
  - A common envelope: `DocumentSpec` (doc_type, filename_stem, language, content). The LLM is forced into this schema via structured output.
- `renderers/` — one pure module per format, `render(spec) -> bytes` + `mime_type` + `extension`. All CPU-bound rendering runs through `asyncio.to_thread` at the call site.
  - **Registry** `RENDERER_REGISTRY: dict[doc_type, Renderer]` with a **boot-time completeness assert** against the `DocumentType` enum (ADR-085 doctrine).
  - **Security**: spreadsheet/csv cell values starting with `=`, `+`, `-`, `@` are prefixed with `'` (proven formula-injection surface); csv encoded `utf-8-sig`; filenames sanitized (path separators, control chars, length ≤ 100, fallback stem) — stored filename on disk stays a UUID (existing anti-traversal convention).
- `document_store.py` — mirror of `image_store.py`: `PendingDocument(url, filename, doc_type, size_bytes, expires_at)`, thread-safe module store keyed by conversation_id, `to_wire_metadata()` single serializer for both emission sites (done chunk + message_metadata).
- `service.py` — orchestrates: LLM structured-output call (llm type `document_generation`, provider/model from `LLMConfigOverrideCache`, usage declared to token tracking) → renderer → `_write_document_file` (`asyncio.to_thread`) → `AttachmentRepository.create` (content_type=DOCUMENT, `expires_at = now + attachments_ttl_hours`) → pending store.

### 4.2 Tool `generate_document`

`src/domains/agents/tools/document_generation_tools.py`, decorated `@registered_tool` + `@track_tool_metrics` + `@rate_limit` (settings-driven lambdas):

```
generate_document(
    instructions: str,          # what the document must contain
    doc_type: str,              # csv|xlsx|docx|pptx|pdf|md|txt
    source_data: str = "",      # optional raw material (e.g. $steps.step_1.web_searches)
    filename: str = "",         # optional user-requested name (sanitized)
    runtime: InjectedToolArg,
)
```

Guards in order (mirror `generate_image`): user_id present → global flag → user opt-in → doc_type validated against enum (repairable? no: wrong enum stays an error per ADR-184 doctrine) → LLM call → render → save → pending store → `UnifiedToolOutput.action_success` with explicit "already displayed, do NOT add a link" message.

**Failure honesty**: if rendering or saving fails AFTER the LLM call, the tool returns `UnifiedToolOutput.failure` with an explicit message (tokens were spent, no document exists — never implicit success; v1.30.4 doctrine).

### 4.3 Catalogue, taxonomy, orchestration

- `src/domains/agents/document_generation/catalogue_manifests.py`: `AgentManifest` (`document_generation_agent`, virtual) + `ToolManifest` (semantic keywords: "create a csv/spreadsheet/report/presentation file", "export as document", "formalize results into a file"…; `tool_category="create"`; published `enum` bound on `doc_type` — an enforced constraint must be published, ADR-184).
- `domain_taxonomy.py`: `document_generation` DomainConfig, `result_key="document_generations"`, `is_routable=True`.
- `catalogue_loader.py`: registration behind `document_generation_enabled` flag (mirror image block).
- `agents/constants.py`: `AGENT_DOCUMENT = "document_generation_agent"`.
- **Timeout family** (ADR-160 doctrine): `_DOCUMENT_TOOL_NAMES` in `parallel_executor.py` with dedicated floor/ceiling settings (LLM long-output call: floor 120 s, ceiling 480 s), so a planner step can never undercut the real latency.

### 4.4 Configuration & flags

- `src/core/config/document_generation.py` — `DocumentGenerationSettings`: `document_generation_enabled`, rate limit calls/window, tool timeout floor/ceiling, `document_generation_max_output_chars` (truncation announced in the document itself when hit). Added to `Settings` MRO; constants in `core/constants.py`; `.env.example` / `.env.prod.example` updated.
- `PlatformCapability.DOCUMENT_GENERATION` + `SystemSettingKey.CAPABILITY_DOCUMENT_GENERATION_ENABLED` (admin runtime switch, `agents=("document_generation_agent",)`).
- `User.document_generation_enabled` opt-in column (default true, `server_default="true"`) + Alembic migration + `user_data_map.py` `_PREFERENCE` entry + users schemas/service plumbing (mirror the 4 image fields — beware the admin-branch-masks-user-path trap: wire BOTH DTO paths).
- LLM type `document_generation` in `LLM_TYPES_REGISTRY` (`CATEGORY_SPECIALIZED`, `power_tier=POWER_TIER_HIGH`, kind chat) + `LLM_DEFAULTS` (sync assert already enforces pairing) + i18n description keys.

### 4.5 Delivery & serving

- `agents/api/service.py`: two symmetric touch points, guarded by the flag — `peek_pending_documents` → `assistant_metadata["generated_documents"]` (archive) and `get_and_clear_pending_documents` → done chunk metadata. Same single `to_wire_metadata` serializer both times.
- `attachments/router.py`: disposition rule becomes `inline` for images AND `application/pdf`; everything else keeps `attachment`.

## 5. Frontend design

- `types/chat.ts`: `GeneratedDocument { url, filename, doc_type, size_bytes, expires_at }` — single declared shape used by SSE mapper, history mapper, reducer (the GeneratedImage lesson: one declaration, zero drift).
- `ChatMessage.tsx`: `GeneratedDocumentCards` — icon per doc_type, filename, human size, expiry notice (same phrasing/component logic as image cards), download link (`<a href>` to the attachment URL; PDF opens in new tab).
- Reducer/`useConversation`: map `generated_documents` from done chunk and from reloaded message metadata.
- Settings > Features: `document_generation_enabled` user toggle (mirror image generation toggle).
- i18n: all card labels, settings labels, tool display name (`i18n_key="generate_document"`) in the 6 locales, strict parity (zh: duplicate `_one`).

## 6. Testing strategy (TDD, per lot)

- **Renderers (pure)**: unit tests per format with **round-trip oracles using the RAG extractors already in the repo** (openpyxl/python-docx/python-pptx/PyMuPDF read back what was written); formula-injection neutralization asserted; BOM asserted; filename sanitization property cases; completeness assert test for the renderer registry.
- **Tool**: guard-order tests (flag off, opt-in off, bad doc_type), LLM failure, render failure after LLM success (honest failure), success path with mocked LLM + tmp storage; thresholds read from `settings`, never hardcoded.
- **Store**: pending store concurrency + wire serializer round-trip.
- **Delivery**: service-level test that done chunk and archived metadata carry identical shapes.
- **Frontend**: vitest for card rendering (with/without expires_at, each doc_type icon, download href), reducer mapping; e2e hermetic journey (mocked SSE done chunk with a generated document → card visible, accessible name, keyboard reachable).
- **Gates**: `task lint`, `task test:backend:unit:fast`, `task test:frontend`, `task ci:fast` before any push; migration replay check for the User column.

## 7. Edge cases handled

- Content larger than `max_tokens` / max chars → truncation stated inside the document and in the tool message (a count shown is a claim — never silent).
- Multiple documents per turn → pending store is a list end-to-end.
- Renderer failure after paid LLM call → explicit failure, no phantom card.
- Attachments capability disabled while document generation enabled → same implicit dependency as images; documented in ADR; card link fails closed (404) rather than silently.
- Non-ASCII filenames → RFC 5987 proven; sanitization still strips separators/control chars.
- Timezone/locale: document language follows the user's language (backend-canonical code via `normalize_language`).
- Concurrency: no per-request state on module singletons; per-call DB sessions via `get_db_context()`.

## 8. Out of scope (v2 candidates, recorded not built)

- `edit_document` (regenerate/amend an existing document — the `edit_image` analog).
- Rich in-chat preview (CSV/XLSX table rendering, PPTX thumbnails).
- Branded PPTX/DOCX templates (custom theme assets).
- ODT/ODS output (odfpy is present; demand unproven — YAGNI).

## 9. Implementation lots

- **Lot 0** — ADR-226 + this spec cross-referenced (INDEX, ADR_INDEX).
- **Lot 1** — Backend foundation: settings module + constants + capability + LLM type + User column + migration + env examples + GDPR map.
- **Lot 2** — Domain module: schemas + renderers (+ registry assert) + document_store + service, fully unit-tested.
- **Lot 3** — Tool + manifests + taxonomy + loader wiring + timeout family + SSE/archive delivery + PDF inline disposition.
- **Lot 4** — Frontend: types, cards, reducer/history mapping, settings toggle, i18n ×6.
- **Lot 5** — Cross-cutting: e2e journey, docs (ARCHITECTURE_AGENT, guides, README surfaces), full gates, ratchet compliance.

Each lot lands with its tests (TDD), inline, no subagents; git operations remain the owner's.
