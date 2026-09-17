# ADR-296 — A mail attachment is read: its text when it has one, the vision slot otherwise

**Date**: 2026-09-17
**Status**: Accepted
**Amends**: ADR-286 (a tool result is projected under a budget, the cut stated), ADR-287 (one e-mail vocabulary at the client boundary), ADR-272 (every platform-paid token answers to both ceilings), ADR-275 (a truncated output is a refusal), ADR-184 (a bound is published)

## Context

`get_emails` lists the attachments of a message (name, type, size, handle) and
stops there: nothing could open one. The owner asked for a ReAct tool that
extracts and reads the attachments of a mail, with the vision model when the
attachment is a picture. Read before writing:

- Gmail had `get_attachment` (bytes by handle), used by the browser proxy and
  the forward path; Microsoft Graph listed attachments with `$expand` and
  downloaded none; the IMAP client read payloads only to forward them, and its
  normaliser published no handle at all. `EmailClientProtocol` had no
  attachment method — the parity rule applies;
- the knowledge spaces already extract fifteen formats
  (`rag_spaces.processing.extract_text`) and already know the shape of a scan
  (`classify_empty_extraction`: pictures and no text layer); PyMuPDF renders a
  page to an image;
- the `vision_analysis` slot had ONE reader (the response node) and was
  missing from the `LLMType` Literal — declared as debt in the slot vocabulary
  guard's `LITERAL_GAP`;
- `emails_tools.py` and `emails/catalogue_manifests.py` sit at their size caps.

## Decision

**One download seam on the three clients, one reading module, one tool.**

- `EmailClientProtocol.download_attachment(message_id, *, attachment_id,
  filename) → EmailAttachmentContent(filename, mime_type, data)` — Gmail
  (`gmail_attachments_mixin.py`, the client's attachment unit extracted so the
  frozen file shrank), Graph (`/attachments` listing then `contentBytes`) and
  IMAP (the part INDEX is the handle the normaliser now publishes). The
  selection is ONE helper (`clients/email_attachments.select_attachment`):
  by handle, else by case-insensitive name, an ambiguous name refused with its
  candidates.
- **A stale handle is not a lie** — measured on a real mailbox 2026-09-17:
  Gmail's `attachmentId` changes between two reads of the same message, so
  the handle a listing served may be gone when the tool re-reads the
  message. The name decides when given; a single part is unambiguous; any
  other case answers `DISAMBIGUATION_REQUIRED` with the CURRENT handles, and
  the manifest tells the model to prefer the file name and to pass both.
- `agents/emails/attachment_content.py` reads BYTES and touches no client:
  the MIME type is read from the magic bytes (the sender's header as a
  fallback), a document goes through `extract_text` in a worker thread, an
  image or a PDF without a text layer is handed to the vision slot as a
  bounded, downscaled set of PNG pages (`email_attachment_vision_max_pages`,
  `email_attachment_image_max_edge`), anything else is refused by name. The
  bound applies to the RASTER too: the render scale is capped so a page never
  rasterises past twice the edge — measured in the cold review, a page 200
  inches a side allocated 829 M pixels before Pillow refused it.
- **The vision call is the turn's spend**: `invoke_with_instrumentation`
  (a declared chokepoint) with the runtime's `RunnableConfig` and the account,
  `short_answer_config` on the slot's own budget (ADR-285), `spend_blocked`
  → `skipped_quota` (never « failed »), a truncated answer → refusal, the
  prompt a versioned file with its one-line scaffold in a lines file
  (ADR-284). `LLM_SPEND_ROADS` declares the module on the TURN road.
- `get_email_attachment_tool` (`tools/email_attachment_tools.py`, a read tool
  of the e-mail agent, `mutation_policy="read"`, both execution modes) bounds
  the download (`email_attachment_max_mb`, stated in the refusal) — and the
  bound travels to the client (`download_attachment(max_bytes=…)`), so a part
  the listing already says is too large is refused BEFORE any byte moves
  (`ensure_within_bound`, one helper for the three clients; the check on the
  bytes stays the net for a listing that knew no size). It serves the text in
  PARTS under `emails_body_part_tokens` like a body (ADR-287), and wraps it as
  **external content** — an attachment is what a stranger sent — on both
  execution paths; the file NAME is a stranger's text too, so the wrapper's
  source attribute is now escaped, single-line and bounded (cold review: a
  name carrying `">` and a line break landed text before the untrusted
  warning). Every refusal is told by name (`_OUTCOME_CODES`).
  `email_attachment_reads_total{route, outcome}` is drawn on dashboard 10
  beside the digest outcomes.
- **A cut page set is stated** (ADR-286): the reading carries `pages_read`
  AND `pages_total`, and the vision prompt receives a `pages_cut` line
  (« only the first N of M are shown ») so the model claims no completeness
  over pages it cannot see.
- The phone excludes the tool by construction (`message_id` is an identifier
  the derivation refuses).

## Consequences

- Measured on dev 2026-09-17 with a real mailbox: a 632 KB PDF attachment
  downloaded through Gmail and extracted to 55 625 characters
  (`route=text outcome=ok`); a 77 KB PNG rendered to one page and read by
  the configured vision slot (`route=vision outcome=ok`, 666 characters).
  A first run of that proof answered `failed`: the harness ran outside the
  application, so `LLMConfigOverrideCache` was empty and the slot fell back
  to its seed default — a reminder that a proof script must load what the
  lifespan loads before it can judge a configuration.
- `vision_analysis` joined the `LLMType` Literal; the slot vocabulary guard's
  gap shrank by one.
- HEIC (an iPhone photo) is decoded: `pillow-heif` joins the runtime image and
  `infrastructure/media/heif.py` registers it lazily where a stranger's picture
  is opened — the upload's HEIC→JPEG conversion, which the router had promised
  since v1 with no codec behind it, works for the first time on the same seam.
- Not done: a vision reading of a PDF that HAS a text layer (charts inside a
  report) — the text route wins; extensible with a flag when a need appears.

## Rejected

- Growing `emails_tools.py` or `catalogue_manifests.py` (both at their cap).
- A ReAct-only manifest: a planner can chain `emails[0].attachments[0]` into
  the tool, and a mode restriction needs a reason (ADR-249's was that the
  planner cannot run a sandbox).
- Reading the vision slot's configuration from the catalogue to decide a
  route: the bytes decide, the slot answers or refuses.
