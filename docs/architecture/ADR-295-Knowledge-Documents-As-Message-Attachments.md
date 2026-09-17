# ADR-295 — A knowledge-space document attaches to a message as a copy, paused space or not

**Date**: 2026-09-17
**Status**: Accepted
**Amends**: ADR-279 (generated assets and the reset's origin filter), ADR-280 (one switch per capability), ADR-286 (a cut is stated), ADR-185 (a count is exact or does not exist)

## Context

The chat's retrieval reads the ACTIVE knowledge spaces alone
(`rag_spaces/retrieval.py`, `get_active_for_user`), and so does the
`search_user_documents` tool. A document indexed in a space the person paused
was therefore unreachable from a question — the only way to ask about it was
to re-activate the whole space, or to re-upload the file. The owner asked for
the composer's « + » to offer, beside the file picker, the documents of the
knowledge spaces, *even the inactive ones*.

Three facts decided the shape:

- the upload pipeline accepts images and PDF only (`ATTACHMENTS_ALLOWED_*`
  defaults) and extracts text from PDF alone, while a knowledge space holds
  fifteen formats and keeps the stored file on disk
  (`document_access.document_file_path`) — so a knowledge document cannot go
  through the upload door as it is;
- what reaches the model is `current_turn_attachments` → `build_vision_message`
  at the response node, in BOTH execution modes, and the metadata is popped at
  the end of the run — the attachment mechanism already carries a document's
  text for one turn without bloating the checkpoint;
- the chunks of a document overlap (`RAG_SPACES_CHUNK_OVERLAP_DEFAULT`), so a
  text rebuilt from `rag_chunks` would repeat itself.

## Decision

**A knowledge document attaches as a COPY, through the attachment mechanism,
and the space is never touched.** `POST /attachments/from-knowledge-document`
(`attachments/knowledge_copy.py`) copies the stored file under a fresh UUID
name in the attachments store, extracts its text through the knowledge
spaces' own pipeline (`rag_spaces.processing.extract_text` — the fifteen
formats, not the upload's allowlist) under `attachments_max_pdf_text_chars`,
and creates a row with `origin = upload`: a conversation reset removes it like
anything the person put in (ADR-279's filter), the TTL sweep expires it, and
the knowledge document keeps its space, its index and its file.

- **Only a `ready` document is offered** — its extraction is proven; anything
  else answers `409 {code: document_not_ready}`, translated by the frontend.
  A document of another account, or of a system space (which belongs to
  nobody), does not exist for the caller (`owned_document`).
- **Both switches must be on**: the route carries the ATTACHMENTS guard (it
  puts a file in) and the RAG_SPACES guard (it reads a space) — the
  route-wiring guard now names the two doors that put a file in.
- **The listing is one statement, page and exact total**
  (`GET /rag-spaces/documents`, mounted BEFORE `/{space_id}` so the literal is
  never read as an id): the `ready` documents of every space the person owns,
  active or not, the space named beside each, a name needle whose LIKE
  wildcards are escaped, the page bound published (`max_limit`).
- **The « + » becomes a menu as soon as it has a second entry**, and only
  then: a browser keeps its one-click file picker when the spaces are off
  (ADR-259's decision), the Android shell keeps its camera entry, and the
  knowledge entry joins last. The picker lists the documents with their space,
  badges a paused space rather than hiding it, searches by name, and bounds
  the selection by the room left in the message
  (`useFileUpload.addServerAttachment` honours the per-message cap and refuses
  a duplicate).
- **A cut is stated to the model**: the document block the response node
  injects (`llm_content._append_document_content`) says « the first N
  characters of the document » when the extracted text sits at the cap — for
  every document attachment, uploads included, which used to be cut in
  silence.

Two defects found on the way and corrected: the attachment hint labels lived
inline in Python and were keyed `zh` where the backend canonical is `zh-CN`,
so every Chinese reader got the English hint — they now come from
`APIMessages.attachment_hint_labels` through `normalize_language`.

## Consequences

- One new edge `attachments → rag_spaces` (no cycle: `rag_spaces` imports
  nothing from `attachments`), confined to `knowledge_copy.py`.
- The turn pays the document's text once, in the response prompt, bounded by
  the existing cap; no model call at attach time.
- The ReAct loop itself still sees only the hint (as for uploads): the
  document text reaches the synthesis, not the tool loop. Measured on dev
  2026-09-17: a `.docx` of a PAUSED space, attached through the endpoint, its
  figure quoted exactly in the answer in pipeline AND in react mode; a reset
  removed the copy (`404`) and left the space document in place.

## Rejected

- **A reference in the message** (a `document_refs` field): every surface the
  attachment path already serves — the hint, the archive metadata, the bubble
  chip, the reset semantics — would have been written a second time.
- **A targeted retrieval over the chosen documents**: bounded to
  `rag_spaces_max_context_tokens` and driven by similarity, it answers « what
  is relevant » where the person asked « read this ».
- **A new `AttachmentOrigin`**: the copy IS what the person put in; a new
  origin would have escaped the reset's `upload` filter for no reason.
