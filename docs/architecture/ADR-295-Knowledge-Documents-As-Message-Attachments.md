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

## Amendment 2026-10-24 — a kept answer and a generated file come back the same way

**Owner request.** Bring back into the current discussion what LIA already gave:
a bookmark, a generated image or document.

**Decision.** Two more doors, the same shape: `POST /attachments/from-bookmark`
attaches a kept answer as the Markdown its knowledge document reads
(`render_bookmark`, ADR-291), whatever its projection state; `POST
/attachments/from-generated` copies a live generated file of the caller (kept, or
before its deadline — ADR-319), an image as an image within the upload's bounds, a
document with its text. Every copy is an `upload`; the three doors share ONE copy
store (`attachments/copy_store.py`: the fresh name, the disk work off the loop, the
commit that withdraws an orphan file). The composer's « + » offers them through ONE
picker (`AttachSourcePickerDialog`), the knowledge picker now one of its sources; and
« Use in the discussion » on the bookmarks and gallery pages is a plain link to the
chat's `?attach=<kind>:<id>`, consumed once (dropped from the address on arrival,
like `?draft=`): a replay can only attach another copy, never send. The « + » stays a
single click where no other source is on. Not measured yet: whether the ReAct loop,
which sees an attachment's hint and not its text (above), misses a kept answer's
text on a follow-up needing tools.


## Amendment 2026-11-12 — the composer takes by upload what it takes by copy

A copy from a knowledge space brought any of the fifteen formats into a message; the
upload beside it still refused everything but an image and a PDF, so a Word document on
the person's desktop had to be put in a space first. The upload now takes the same
formats.

- **One list for the two doors.** `EXTRACTABLE_DOCUMENT_TYPES_DEFAULT` is the default of
  both `ATTACHMENTS_ALLOWED_DOC_TYPES` and `RAG_SPACES_ALLOWED_TYPES`; each stays its
  operator's to narrow. `attachments/document_formats.DOCUMENT_FORMATS` names each format
  once, and an import-time assert refuses one no reader of the spaces can extract
  (`rag_spaces.processing.EXTRACTABLE_CONTENT_TYPES`).
- **The type is what the file IS.** The request's declared type is never read. A signed
  format is recognised by its bytes; the Office and OpenDocument archives open on the
  same four bytes, so an archive is told apart by what it contains (the part an Office
  file is built around, the `mimetype` member an OpenDocument or EPUB file declares
  itself with) — read from the member NAMES and one member of a few dozen bytes, nothing
  inflated. An unsigned format (text, Markdown, CSV, HTML, JSON, XML) is named by its
  extension once its content is proven to be text: a NUL byte refuses it, a legacy
  encoding does not. The decision needs the whole content — an archive names itself at
  its end — so it runs after the bounded read, off the event loop.
- **Published to the composer** (ADR-184): `/config` carries `attachments.image_types`
  and `attachments.document_extensions`, and the picker and the drop zone filter on the
  NAME — a browser reports no type for a `.md` and a spreadsheet's for a `.csv`.
- **A text that cannot be extracted costs the text, never the upload**, as a scanned PDF
  always did; the failure is logged by its type.
- **A zipped document is not read past what it declares it inflates to.** A file sent
  small can inflate large, and its readers inflate whole parts in memory, inside the
  upload request. The sum an archive declares in its directory is a real bound (a zip
  reader never inflates a member past its declared size) and is read without inflating
  anything: past `ATTACHMENTS_MAX_INFLATED_MB` the reader is never started — the file is
  kept, its text is not read, the fact is logged. This bound is the composer's upload's: a
  knowledge space keeps its own limits, on a file's size and on the chunks it indexes.
- **A text file is read in the letters it was written in** (same day). A text file names
  no encoding, and every reader of a text format opened it as UTF-8 with replacement: a
  spreadsheet export from a French Windows desktop reached the model, and a space's
  index, with U+FFFD for every accent, and a « CSV UTF-8 » kept its byte-order mark as
  the first letter of its first cell. The readers now ask ONE door,
  `core/text_decoding.decode_text`: a UTF-16 mark is believed, bytes that are UTF-8 are
  UTF-8, and bytes that are not are told apart by what they mostly are — a UTF-8 text
  with a damaged byte loses that byte alone, a text of single-byte accents is read in
  Windows' letters (cp1252). No other legacy encoding is guessed. The Tools' preview
  (`workbench/previews.py`), which held the rule first, reads the same door. Line ends
  are `\n` as text mode always gave them.

**Operator note.** The environment templates used to state
`ATTACHMENTS_ALLOWED_DOC_TYPES=application/pdf`. An instance whose `.env` kept that line
keeps PDFs alone — the environment overrides the constant: remove the line, or update it.

**Left as it was.** A served upload keeps `Content-Disposition: attachment` unless it is
an image or a PDF: an uploaded HTML file is downloaded, never rendered on the API's
origin. A text Windows writes as UTF-16 holds a NUL byte in every ASCII letter, the byte
that refuses a binary: its byte-order mark says what it is, and the composer accepts it
when what follows the mark decodes whole and holds no NUL character
(`document_formats._is_utf16_text`); its readers read it through the same door.

Guards: `tests/unit/domains/attachments/test_document_formats.py` (real files written by
the libraries their readers use), `tests/unit/core/test_text_decoding.py`,
`tests/unit/domains/rag_spaces/test_text_readers_encoding.py` (each text reader on a
Windows file, and an AST guard refusing a reader that decodes by itself),
`test_document_upload.py`,
`tests/unit/api/test_client_config_flags.py`, and on the web
`src/lib/__tests__/attachment-formats.test.ts` and `ChatInput.test.tsx`.
