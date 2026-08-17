# AI Document Generation (ADR-226)

> Downloadable documents (csv, xlsx, docx, pptx, pdf, md, txt) written by a
> dedicated LLM slot, rendered locally with the libraries already embedded for
> RAG extraction, stored as TTL attachments and delivered as cards below the
> assistant response. Architectural mirror of
> [IMAGE_GENERATION.md](./IMAGE_GENERATION.md).

## Overview

`generate_document(instructions, doc_type, source_data?, filename?)` gives the
assistant its "produce a file" capability in both execution modes: as a plan
step in pipeline mode (chaining research → document via `$steps` templating on
`source_data`) and as a regular tool in ReAct mode.

### Features

- 7 output formats behind one tool, validated against a closed enum that is
  **published** to the planner (ADR-184 doctrine, `_manifest_to_dict` now
  forwards `enum` constraints like `min`/`max`).
- Content produced by the `document_generation` LLM slot (admin-configurable
  in LLM Config; default `openai/gpt-4.1`) via structured output, with the
  schema selected per format family BEFORE the call (strict-mode compatible):
  tabular (csv/xlsx), sectioned (docx/pdf/md/txt), slides (pptx).
- Pure renderers, zero new dependency: csv stdlib (`utf-8-sig` BOM for Excel),
  openpyxl, python-docx, python-pptx, PyMuPDF Story (escaped HTML → paged A4).
- Cards below the response: live via the SSE done chunk, after reload via
  `message_metadata` — ONE serializer (`document_store.to_wire_metadata`),
  called through the branchless `delivery.py` helpers so the streaming hotspot
  gains no complexity.
- Download vs open: every card is a native `<a>`; PDF opens in a tab (the
  attachments route serves `application/pdf` inline, like images), everything
  else carries the `download` attribute with a human filename.

## Architecture

### Data Flow

```
generate_document tool (guards: user, flag, opt-in, doc_type enum)
  └─ DocumentGenerationService.generate_document_for_user
       ├─ load_document_prompt (path-based domain loader — no agents import,
       │   the agents↔document_generation cycle stays broken, telephony pattern)
       ├─ get_structured_output_with_retry (schema by family, provider from
       │   LLM config, run's RunnableConfig → token tracking node
       │   "document_generation")
       ├─ render_document (pure, asyncio.to_thread)
       ├─ Attachment row (content_type="document", expires_at = now +
       │   attachments_ttl_hours → existing 6h cleanup job purges it)
       └─ document_store.store_pending_document
            ├─ archive: delivery.attach_archived_documents (peek)
            └─ done chunk: delivery.attach_done_documents (clear)
```

### Key Design Decisions

- **Internal dedicated LLM, not planner-supplied content**: the planner is
  economical by design; a document is a long artefact. `source_data` remains
  the raw-material channel (`$steps` in pipeline, inline in ReAct), capped by
  `document_generation_max_source_chars` with the truncation REPORTED in the
  tool result.
- **Spreadsheet-injection neutralization is mandatory**: the 2026-08-17 probe
  proved openpyxl stores `"=1+2"` as a real formula. `neutralize_formula`
  quotes active values (`= + - @`, tab, CR) and exempts plain signed numbers
  (`-5.2` is data). XLSX sheet titles are sanitized and deduplicated
  (openpyxl rejects `[]:*?/\` and duplicates).
- **Honest failure**: any failure after the paid LLM call returns an explicit
  `UnifiedToolOutput.failure` — no phantom card, no implicit success
  (v1.30.4 doctrine).
- **No pricing table**: cost = LLM tokens through the standard tracking (the
  default model has active `llm_pricing` seed rows, so tracked cost is
  non-zero).
- **Completeness asserted at import**: `SCHEMA_BY_DOC_TYPE`, `RENDERERS`,
  `DOCUMENT_MIME_TYPES`, `DOCUMENT_EXTENSIONS` are all keyed by
  `DocumentType` and refuse a partial map (ADR-085).

## File Structure

Backend domain: `apps/api/src/domains/document_generation/` — `schemas.py`
(content models), `sanitize.py`, `renderers.py`, `document_store.py`,
`delivery.py`, `service.py`, `prompts.py`. Tool:
`domains/agents/tools/document_generation_tools.py`. Catalogue:
`domains/agents/document_generation/catalogue_manifests.py`; the domain lives
in `registry/program_domain_configs.py` (taxonomy extension point). Prompt:
`prompts/v1/document_generation_prompt.txt`.

Frontend: `GeneratedDocument` type (`types/chat.ts`, single declaration),
`GeneratedDocumentCards` in `ChatMessage.tsx`,
`components/settings/DocumentGenerationSettings.tsx` (per-user opt-in),
settings search entry `document-generation`.

## Expiry surfaced to the client (N2)

`expires_at` travels on every card (wire + archive, same serializer). The
frontend reuses the image-cards expiry notice (`classifyImageExpiry`) with a
document-specific "expired" copy; unknown deadline → the UI says nothing.

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `DOCUMENT_GENERATION_ENABLED` | `true` | Deployment ceiling; also gates catalogue + tool registration |
| `DOCUMENT_GENERATION_RATE_LIMIT_CALLS` / `_WINDOW` | 10 / 300 s | Per-user sliding window on the tool |
| `DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS` | 120.0 | Executor floor (ADR-160 family) |
| `MAX_DOCUMENT_GENERATION_TOOL_TIMEOUT_SECONDS` | 480.0 | Executor ceiling (see [TIMEOUT_REGISTRY.md](./TIMEOUT_REGISTRY.md)) |
| `DOCUMENT_GENERATION_MAX_SOURCE_CHARS` | 60000 | `source_data` cap forwarded to the LLM (truncation reported) |

### Switches (three levels)

1. Env flag `DOCUMENT_GENERATION_ENABLED` (deployment ceiling).
2. Admin runtime capability `PlatformCapability.DOCUMENT_GENERATION`
   (Administration > Capabilities — removes the agent from the catalogue).
3. Per-user opt-in `User.document_generation_enabled`
   (Settings > Preferences > Document generation).

### Admin LLM Config

Slot `document_generation` (category Specialized, power tier high): provider,
model, temperature, `max_tokens` (bounds the largest producible document — an
overflow fails honestly rather than shipping a silently truncated file) and
timeout are admin-tunable like every other slot.
