# Meeting template library, auto-selection, reformatting — and four adjustments

- **Date**: 2026-09-03
- **Status**: DESIGN — awaiting owner approval (no code written)
- **Builds on**: ADR-258, `2026-09-02-meeting-recording-and-minutes-design.md`,
  `docs/technical/MEETINGS.md`
- **Scope**: (A) minutes email from the platform SMTP sender, (B) bulk delete of
  meetings, (C) readable template editor, (D) recording start/stop surfaces,
  (E) template library + categories + automatic selection + reformat/copy,
  (F) knowledge spaces: download and move documents.

Every statement below was read in the code on 2026-09-03 (file:line cited) or
measured by running the existing suites. Baseline before any change:
`pytest tests/unit/domains/meetings` → **123 passed**; vitest on
`components/meetings`, `lib/meetings`, `dashboard/meetings`, `MeetingsSettings`,
`components/spaces` → **20 files, 143 passed**.

---

## 1. What exists today (verified)

| Fact | Evidence |
|---|---|
| ONE template per user: `meeting_templates` row with `is_default=true`, partial unique index `uq_meeting_templates_one_default_per_user`; the built-in default lives in code (`templates.py`) with labels in `core/i18n_meetings.py` | `models.py:246-268`, `templates.py:33-79` |
| Processing and regeneration both read **the user's default template**, never a per-meeting choice; the meeting only keeps `template_snapshot` (sections, no name) | `processing.py:536-537`, `689-690`, `models.py:216` |
| Section kinds: `paragraph` (≤ 8 000 chars), `bullets` (item ≤ 1 000), `topics` (summary ≤ 4 000), `action_items`. A whole-meeting **transcript does not fit any kind** (2 h of speech ≈ 50 000+ chars) | `schemas.py:117-140` |
| `meeting_synthesis` slot: `gpt-4.1`, `max_tokens=8000` → one structured call cannot output a rewritten 2 h transcript (~18 k tokens) | `llm_config/constants.py:1156-1165` |
| Minutes email goes through the user's **connector** (Google/Microsoft/Apple), 409 `email_connector_missing` when none; `EmailService` (platform SMTP, `From = APPLICATION_SMTP_FROM`) exists and is used by auth flows and the demo report — with a **synchronous `smtplib` exchange inside an `async def`** (event-loop blocking, no `to_thread`) | `delivery.py:53-108`, `email_service.py:35-97`, `security.py:309-339` |
| Regeneration: `READY` + `stage=synthesizing`; a hard kill leaves the stage set forever (`regeneration_in_progress` on every later attempt) — **no reaper covers it** (the job reaper only handles `PROCESSING` leases and live recordings) | `repository.py:begin_regenerate`, `reapers.py:32-58` |
| List page: one row per meeting, no selection; detail page toolbar: Edit / PDF / Email / « Rebuild with my template » / Reset | `dashboard/meetings/page.tsx`, `MeetingDetailPanels.tsx:190-260` |
| Template editor: every section shows Heading + Format + a 2-row instruction textarea, always expanded | `MeetingTemplateEditor.tsx` |
| Recording: start AND stop live in the composer's « + » menu (`RecordMenuItem`), stop also in the banner; the banner is rendered at the top of `<main>` and is **not sticky** (a scrolled page hides it) | `ChatInput.tsx:351-462`, `MeetingRecorderProvider.tsx:157-160`, `layout.tsx:277-282` |
| Knowledge spaces: documents have no download and no move; `rag_chunks.space_id` is **denormalized** and the physical file lives under `user_id/space_id/`, so a move touches the row, its chunks and the file; `DocumentRow` still uses `opacity-0 group-hover` for delete (ADR-208 violation) | `rag_spaces/models.py:472-492`, `service.py:463-500`, `DocumentRow.tsx:70-80` |
| Generational retrieval pins `serving_embedding_model` per space **only during a reindex** (`pin_serving_for_spaces` at `reindex.py:226`, cleared at `:264`); in steady state every space serves NULL | `retrieval.py:380-400` |

---

## 2. Decisions (with alternatives rejected)

### A. Minutes email from `APPLICATION_SMTP_FROM`

- `delivery.send_minutes_email` calls `get_email_service().send_email(to, subject, html_body, text_body)`; `text_body = render_markdown(...)` (multipart/alternative for free — the ONE serializer already produces it).
- `EmailService.send_email` returns `False` on failure → `MinutesDeliveryError("email_send_failed")` (502, existing code). The connector resolution, `_resolve_email_client` and the code `email_connector_missing` are **deleted** everywhere (backend, 6 locales, tests, spec table §API, settings hint « Sent through your connected email account » → « Sent by LIA from its own address »).
- Boy Scout (touched file, Systemic Rules « no synchronous network on an async path »): the `smtplib` block of `EmailService.send_email` moves into a sync helper executed with `asyncio.to_thread`. Behaviour and signature unchanged; one test with a patched `smtplib.SMTP` asserts the thread hand-off and the `From` header.
- Subject: `"{minutes_label} · {title}"` (`get_header_label("minutes")`, localized) instead of the bare title — a mailbox lists many subjects; « Compte rendu de réunion · Point projet » is self-explanatory. *Owner may keep the bare title.*
- Edge: SMTP unconfigured (default `localhost:587`) → connection refused → 502 `email_send_failed`, the auto-email path keeps its warning log. No « SMTP configured » flag is invented (YAGNI; an operator who enables meetings configures SMTP like they do for account emails).

### B. Bulk delete of meetings

- API: `POST /meetings/bulk-delete` `{ids: list[UUID]}` (1..100) → `{deleted: [id], skipped: [{id, code}]}`. Per id, sequentially through the existing `MeetingService.delete` (projection first, then row, then files — the contract proven by the third runtime proof). Skipped with a stable code: `meeting_not_found` (foreign/absent), `meeting_in_progress` (`processing`, and ALSO `recording`/`interrupted` — discarding a live capture belongs to the banner, whose client holds the upload queue). Never a partial failure disguised as success: the response lists both sets, the UI states both counts.
- UI (list page): a native `Checkbox` per row (label « Select “title” »), rows in `processing`/live carry `aria-disabled` + handler guard (frontend CLAUDE.md: never `disabled` on a focused control). A selection bar appears above the list when ≥ 1 selected: exact count, « Select all on this page » (indeterminate state), **Delete (N)** as a solid red button at the toolbar geometry (ADR-207: bulk destruction). Confirmation through `useConfirm`; toast « N deleted · M skipped (in progress) »; refetch; when the page empties and `offset > 0`, step back one page. Selection clears on page change.

### C. Readable template editor

Each section becomes: **header row** « Section N » + Heading input + Format select (+ up/down/remove as today), and below it a **disclosure** « What LIA must put in this section » (`<button aria-expanded>` + `aria-controls`), **collapsed by default** with a one-line muted preview of the instruction. Expanded → the textarea. A freshly added section opens automatically (its instruction is empty and required); a collapsed section with an empty instruction shows an inline error marker (`aria-invalid` on the textarea, a red « Instruction missing » caption in the header) so the Save guard (`valid`) is explained, not silent. Props API unchanged (`sections`, `onChange`) → `MeetingsSettings` and the new library page share it.

### D. Recording start / stop surfaces (owner decision required)

Why « + » reads wrong: « + » means *add to this message*; a recording is a dashboard-level session, not an attachment; and Stop is offered in two places (menu + banner) while the banner itself can scroll out of view.

Three options, all keeping the recorder in the layout (`MeetingRecorderProvider`), the banner as the detailed status and the `/meeting` slash command:

| | Start | Stop | Cost / risk |
|---|---|---|---|
| **1. Header control (recommended)** | ≥ `lg`: one 44 px icon toggle among the header controls (next to `VoiceToggle` — same component shape: idle = « Record a meeting », live = red pulsing dot + elapsed on `xl`, click = Stop with the banner's confirm). < `lg`: an entry « Record a meeting » in the `MobileNavMenu` the logo opens (the phone's home for everything). Plus a solid primary CTA « Record a meeting » on the Meetings page (`SectionToolbar`). | ONE place: the banner, made `sticky top-16 z-40` under the header so it is visible on every page at every scroll position (« a recording that cannot be seen cannot be stopped » — today it can be scrolled away). The header toggle mirrors Stop on desktop. | « + » goes back to the plain file picker (the menu code is deleted). Header row must be re-measured at 1024–1280 px (the band the reachability spec pins); < `lg` nothing is added to the row (measured: at 390 px a 7th 44 px control would overflow by ~26 px). |
| 2. Composer button | A dedicated `Disc` button in the composer row next to « + ». | Same button while live + sticky banner. | Shrinks the typing area the owner just arbitrated (2026-09-03); only reachable from the chat page while the recording is dashboard-wide. |
| 3. Page + command only | Meetings page CTA + `/meeting` command; « + » keeps « Record » as a secondary entry, loses « Stop ». | Sticky banner only. | Smallest change; weakest discoverability from the chat; « + » still hosts a non-attachment action. |

Common to all: the banner gains, while recording, a compact « Minutes format: Automatic ▾ » select (the per-meeting template choice, §E.6) — the one moment the user knows what they are recording.

### E. Template library, categories, automatic selection, reformat / copy

#### E.1 Identity of a template: a `TemplateRef`

`builtin:<key>` (catalogue, code, read-only, localized live) or `user:<uuid>` (a `meeting_templates` row). A value object with `parse`/`str`, validated at the API boundary (unknown builtin → 422; user row not owned → 404). Rationale against materializing built-ins as rows per user: ~26 rows × users, frozen in one language, impossible to improve in a release. A built-in is customized by **duplicating** it (E.4).

#### E.2 Schema (one migration `d9e0f1a2b3c4_meeting_template_library`, revises `c8d9e0f1a2b3`)

- `meeting_templates`: `+ description Text NULL`, `+ category String(30) NOT NULL server_default 'custom'`, `+ builtin_key String(60) NULL` (which built-in it was duplicated from, informative). `- is_default` and its partial index — **after** the data step below. Bound: `MEETINGS_MAX_USER_TEMPLATES` (setting, default 50).
- `meeting_preferences`: `+ default_template_ref String(80) NULL` (`NULL` = automatic).
- `meetings`: `+ template_ref String(80) NULL`, `+ template_name String(120) NULL`, `+ template_selection String(12) NULL` (`auto` | `user` | `preference`), `+ template_selection_reason String(300) NULL`, `+ source_meeting_id UUID FK meetings SET NULL` (reformatted copies).
- Data step (upgrade): every `meeting_templates` row with `is_default=true` → `meeting_preferences.default_template_ref = 'user:<id>'` (row created if absent). **Rationale**: a user who shaped their template yesterday keeps getting it today; automatic selection is the default for everyone who never edited one. *Owner may prefer « automatic for everyone » — then the data step is dropped and the custom template simply stays in the library.* Existing `meetings` rows: `template_selection='preference'`, `template_name` = their user template's name when one exists, else the localized default name from the user's `language` (a 6-entry dict in the migration). Downgrade recreates `is_default` from the preference.
- `task db:migrate:replay-check` is part of the plan.

#### E.3 Catalogue (code) + i18n (data module)

`domains/meetings/template_catalogue.py`: `BuiltinTemplate(key, category, auto_selectable, sections: [(key, kind, instruction_en)])` + `BUILTIN_TEMPLATES` tuple, `builtin_sections(key, language)`. Names, descriptions and section labels ×6 languages in a new data module `core/i18n_meeting_templates.py` (exempt from the size ratchet like every `core/i18n_*`). Boot-time completeness asserts (ADR-085): every builtin key has a name/description in the six languages; every section key of every builtin has a label in the six; every instruction ≤ 600 chars, ≤ 12 sections, keys match `SECTION_KEY_PATTERN` (the exact bounds `MeetingTemplateUpdate` enforces — verified by the existing test `test_template_update_rejects_duplicate_keys_and_bad_slugs`). The current default becomes `builtin:default_minutes` (its six section tables move from `i18n_meetings.py` into the new module; `default_template()` keeps its name as a thin alias for one release).

Categories (`TemplateCategory`, frontend labels ×6): `meeting`, `transcript`, `analysis`, `business`, `technical`, `personal`, `learning`, `custom` (the user's own).

Proposed built-ins (26 — the owner prunes):

| Category | Key | From |
|---|---|---|
| transcript | `transcript_clean` (normalized, reformulated: hesitations, self-corrections and disfluencies removed, punctuation, nothing added or lost), `transcript_professional` (same + professional register), `transcript_with_summary` (clean transcript preceded by a summary) | owner request |
| meeting | `default_minutes` (today's), `key_points_decisions_tasks`, `meeting_secretary`, `meeting_highlights`, `it_project_meeting`, `team_meeting_sentiment`, `daily_standup`, `one_on_one`, `hiring_interview`, `brainstorming` | modeles.txt + additions |
| analysis | `intent_analysis`, `speaker_psychology` (with the « not a diagnosis » caveat inside the instruction), `power_dynamics`, `behavior_analyst`, `quantitative_data` (as `topics`: element / value · unit / context — no table kind) | modeles.txt |
| business | `bant_analysis`, `consulting_session`, `requirements_gathering`, `sales_discovery_call` | modeles.txt + addition |
| technical | `technical_deep_dive` (the radial mind-map is dropped: no image kind), `it_topics_for_clients` (the « German output » and « ChatGPT level 3 » quirks dropped: output language is the user's) | modeles.txt |
| personal | `medical_appointment`, `car_garage_appointment`, `bank_advisor_appointment`, `legal_consultation` | owner request + addition |
| learning | `lecture_notes`, `training_workshop` | owner request |

Two modeles.txt entries are NOT templates for a recording and are left out on purpose: « Réécriveur – Simple, Clair et Concis » (a text rewriting prompt; it is subsumed by `transcript_clean`) and the BANT example header (dates/participants are header fields we already own).

#### E.4 Library API (static paths declared before `/{meeting_id}`, as `/active` already is)

| Method | Path | Notes |
|---|---|---|
| GET | `/meetings/templates` | `{items: [{ref, name, description, category, builtin, sections_count, editable}], max_user_templates}` — built-ins localized in `user.language`, user rows as stored |
| GET | `/meetings/templates/{ref}` | full template with sections |
| POST | `/meetings/templates` | `{name, description?, category, sections}` or `{duplicate_of: ref, name?}` (server copies sections + category, `builtin_key` set); 409 `template_limit_reached` |
| PUT | `/meetings/templates/{ref}` | user rows only; built-in → 409 `template_readonly` |
| DELETE | `/meetings/templates/{ref}` | user rows only; if it is the preference's default, the preference resets to automatic in the same transaction (meetings keep their `template_snapshot` + `template_name`, so nothing dangles) |
| — | `/meetings/template` (GET/PUT/DELETE) | **removed** (single client; `useMeetingTemplate` replaced) |

Preferences (`PUT /meetings/preferences`) gain `default_template_ref: string | null`.

#### E.5 Selection at processing time (`template_resolution.py`, one function, one precedence)

1. `meeting.template_ref` set by the user for THIS meeting (start body or banner select, E.6) → `user`;
2. else `preference.default_template_ref` → `preference` (no model call);
3. else, when `MEETINGS_TEMPLATE_AUTO_SELECT_ENABLED`, one structured call `TemplateChoice{template_key, confidence, reason}` on the `meeting_synthesis` slot (same `TokenCaptureHandler`, tokens counted in the meeting's synthesis spend), inputs: the catalogue of candidates (built-ins with `auto_selectable`, plus the user's own templates by name/description), the calendar title hint, and a **bounded transcript excerpt** (head + evenly sampled slices, `MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS`, constant) → `auto`; below `MEETINGS_TEMPLATE_AUTO_MIN_CONFIDENCE` (setting) or on `StructuredOutputError` → `builtin:default_minutes` with `reason` = the fallback cause. **Never fails the meeting**; counted by `meeting_template_selection_total{outcome=auto|fallback|preference|user}` with a panel in `27-meetings.json` (metric ratchet: a metric nobody can see is a metric nobody acts on).

Transcript templates are `auto_selectable=False`: a clean transcript costs an output the size of the meeting and is a deliberate choice, never a guess. *Owner decision.*

The chosen sections, ref, name, selection and reason are stored by `_completion_values` (and by regeneration/reformat). Regeneration reads **the meeting's own** `template_ref` (today: the user's default — a coupling this removes); a dangling `user:` ref (row deleted) falls back to `template_snapshot` + `template_name`, so « Rebuild » always works.

#### E.6 Per-meeting choice and reformat

- `POST /meetings` body gains `template_ref?`; while live, the banner's « Minutes format » select writes it through `PATCH /meetings/{id}` (`MeetingPatchRequest.template_ref`, accepted on `recording|interrupted|stopped`, 409 `report_not_ready`-family code `template_locked` once processing started).
- `POST /meetings/{id}/reformat` `{template_ref, mode: "replace" | "copy"}` → 202:
  - **replace**: `begin_regenerate` stores the new ref/name/selection=`user` then `launch_regenerate` (old minutes readable until the new ones are published — unchanged contract). The existing « Rebuild with my template » button becomes « Rebuild » (same template) and « Change the format… » (chooser).
  - **copy**: a new `meetings` row, `status=ready`, `stage=synthesizing`, `report_* = NULL`, `source_meeting_id`, copying the facts (times, timezone, location, calendar, `stt_provider/model/diarized/detected_language/audio_seconds`, `audio_duration_seconds`, `audio_gaps`, the encrypted transcript — same Fernet key, same ciphertext), **no audio** (`audio_path=NULL`, `audio_purged_at=now`), `stt_cost_eur=NULL` (paid once, by the source; the copy's total is its own synthesis), `index_state=pending`; then `launch_regenerate(copy)`. Returns `{id: <copy>}`; the page navigates there. The copy is indexed as its own RAG document (two minutes = two documents; a clean transcript is precisely what RAG questions want) and is **not** announced in the chat (the user is on the page). Deleting the source keeps the copies (SET NULL); the detail shows « Reformatted copy of … » and the source shows « N copies ».
- Reaper (closes a gap that predates this work): `READY` rows with `stage IS NOT NULL` older than `meetings_job_lease_ttl_seconds` → `stage=NULL`, `last_error_code=regeneration_interrupted`; a copy left without `report_current` shows a « writing failed » panel with « Try again » (= reformat replace, same template) and Delete.

#### E.7 A fifth section kind: `transcript`

Required by the transcript templates (§1: nothing existing can hold 50 000+ chars, and the slot's `max_tokens=8000` cannot emit them in one call).

- Schema: `SectionKind.TRANSCRIPT`; `ReportSection.transcript: list[TranscriptLine{speaker, start, text}]`; `is_empty`; `_REPAIRERS[TRANSCRIPT]` (the completeness assert refuses to import without it); MD/PDF/HTML/UI renderers (`**S1 [00:12]** text` paragraphs); editor = one textarea per turn (speaker read-only, `participants` renames apply).
- Generation: `synthesize_minutes` splits the template: transcript sections go through `rewrite_transcript(turns, instruction)` — parts cut **at turn boundaries** (`MEETINGS_REWRITE_PART_CHARS`, constant, sized so a part's output stays under the slot's `max_tokens`), one structured call per part (`meeting_transcript_rewrite_prompt.txt`, the section's `instruction` injected as the style contract, output language = transcript language — a transcript is not translated), answer `RewrittenTurns{turns:[{index, text}]}` validated against the input turn indexes (missing → original text kept, extra → dropped; a part whose output is under `MEETINGS_REWRITE_MIN_RATIO` of its input is retried once, then kept with a logged warning — measured with fakes only, never with a live model in tests). The other sections (and title/participants) go through today's single structured call; a template with only transcript sections still makes that call for title/participants with an empty section list. Cost is real (≈ input size in output tokens) and is tracked like every pass; the reformat dialog says so.
- `_summary_text` (notification) learns the kind: first 300 chars of the first turns.

#### E.8 Frontend

- `types/meetings.ts`, `lib/meetings/api.ts`, `hooks/useMeetingTemplates.ts` (list/get/create/update/delete/duplicate), `useMeeting.reformat`.
- **Library page** `app/[lng]/dashboard/meetings/templates/page.tsx` (static segment wins over `[id]` in Next; the backend declares `/templates` before `/{meeting_id}`): `SectionToolbar` (primary « New template », count), one `Accordion` per category (« My templates » first, then the seven built-in categories), rows = name + description + sections count + `RowActions` (Preview, Duplicate; Edit/Delete on user rows). Create/Edit/Duplicate open an inline editor (name, description, category select, the §C editor, Save/Cancel); Preview renders the sections read-only. A dedicated page rather than the settings accordion because 26+ entries are content the user browses, not a preference.
- **Settings** `MeetingsSettings`: preferences gain « Default minutes format » (grouped select, « Automatic (LIA chooses) » first); the template section becomes a short summary + link « Manage my templates (N) ». Settings search keywords ×6 updated.
- **Meetings page**: toolbar with « Record a meeting » (D) and « Templates »; rows show the template name in the meta line; bulk selection (B).
- **Detail page**: fact « Format: {name} · chosen automatically / by you / your default », a `title` with the model's reason; toolbar « Change the format… » → `ReformatDialog` (grouped select preselecting the current template, radio Replace / Create a copy, a cost note, transcript templates flagged « long, paid like a full rewrite »); `report === null && stage !== null` → « Writing the minutes » panel (polling already covers `stage !== null`); « Reformatted copy of … » / « N copies » links; transcript kind in view and editor.
- **Chat card** `MeetingMinutesCard`: one line « Format: {template_name} » (metadata gains `template_name`).
- i18n ×6: composer/banner/list/detail/templates/errors keys (≈ 70 keys), `settings.search.keywords.meetings`.

### F. Knowledge spaces: download and move documents

Backend (`rag_spaces`):
- `document_file_path(document)` helper (resolve + containment, the `indexing._document_path` doctrine) reused by delete (Boy Scout), download, archive and move; `_owned_document(space_id, document_id, user_id)` replaces the three copy-pasted ownership checks.
- `GET /rag-spaces/{space_id}/documents/{document_id}/download` → `FileResponse` (RFC 5987 filename like the minutes PDF; 404 `document_file_missing` when the disk lost it). Works for `upload`, `drive` (the synced file is on disk) and `meeting` (Markdown).
- `GET /rag-spaces/{space_id}/documents/archive?ids=a,b,c` (1..`rag_spaces_max_docs_per_space`; ~3.7 KB of URL at 100 ids) → a zip built with `asyncio.to_thread` into a temp file, `FileResponse(background=remove)`; duplicate names suffixed `(2)`; files missing on disk listed in a `_missing.txt` member (never silently dropped); total `file_size` above `RAG_SPACES_ARCHIVE_MAX_MB` (setting, default 200) → 413 `archive_too_large` with the limit in `detail`. A GET so the browser follows a top-level navigation (cookie rides along, native shells included — the PDF precedent).
- `POST /rag-spaces/{space_id}/documents/move` `{ids, target_space_id}` → `{moved: [id], skipped: [{id, code}]}`. Per document: target owned, not system, ≠ source, under the doc cap counting the incoming ones (`document_limit_exceeded`); `source_type == upload` only (`document_managed_by_drive`: the sync would re-create it in its source's space and its removal detection reads the source; `document_managed_by_meetings`: the meeting rewrites its document in the space found by `kind`); terminal status only (`document_busy`); refused wholesale with 409 `reindex_in_progress` while `get_reindex_status().in_progress` (spaces are pinned to generations only then — §1). Order per document: UPDATE `rag_documents.space_id` + UPDATE `rag_chunks.space_id WHERE document_id` (new `RAGChunkRepository.move_to_space`), commit, then `os.replace` of the file (same root → an atomic rename); a rename failure reverts the two UPDATEs and reports `document_move_failed`. The row is the authority; the residual crash window (between commit and rename) is logged and its symptom is a `document_file_missing` on download, never a lost document.
- Optional (cheap once selection exists, not requested): `POST /rag-spaces/{space_id}/documents/bulk-delete`.

Frontend (space detail page):
- `DocumentRow` → native `Checkbox` (label « Select “name” ») + `RowActions` (Download as a link, Move… for `upload` rows, Delete) — retiring the `opacity-0 group-hover` delete (ADR-208).
- Selection bar when ≥ 1 selected: exact count, select all, **Download (zip)** (an `<a href>` to the archive GET), **Move to…** (`MoveDocumentsDialog`: target from `useSpaces()` minus the current one, with document counts; result toast states moved and skipped with reasons; rows that cannot move are said so before submitting), Delete (if the optional endpoint is kept).

---

## 3. Settings, constants, observability

- Settings (`core/config/meetings.py`, `.env.example` §87, prod examples): `MEETINGS_TEMPLATE_AUTO_SELECT_ENABLED=true`, `MEETINGS_TEMPLATE_AUTO_MIN_CONFIDENCE=0.5`, `MEETINGS_MAX_USER_TEMPLATES=50`; (`rag_spaces`) `RAG_SPACES_ARCHIVE_MAX_MB=200`.
- Constants: `MEETINGS_TEMPLATE_AUTO_EXCERPT_CHARS=6000`, `MEETINGS_REWRITE_PART_CHARS=12000`, `MEETINGS_REWRITE_MIN_RATIO=0.4`, `MEETINGS_BULK_MAX=100`, `MEETINGS_TEMPLATE_REF_MAX=80`.
- Prompts: `meeting_template_selection_prompt.txt`, `meeting_transcript_rewrite_prompt.txt` (added to `PromptName` and `MeetingPromptName`; the literal-sync test guards it). No number in prose — bounds arrive as placeholders.
- Metric: `meeting_template_selection_total{outcome}` + Grafana panel (`or vector(0)`, `"noValue": "0"`).
- No new LLM slot: selection and rewriting run on `meeting_synthesis` (structured output verified at the call site).

## 4. Edge cases (each with a test)

| Case | Behaviour |
|---|---|
| Auto-selection call fails / low confidence | `default_minutes`, `selection=auto`, reason states the fallback; meeting READY |
| User deletes the template a meeting used | meeting keeps snapshot + name; Rebuild uses the snapshot |
| User deletes the template set as default preference | preference → automatic in the same transaction, toast says so |
| Duplicate a built-in in `zh` then switch UI language | the row keeps its Chinese labels (content, not chrome) — stated in the library page |
| 51st user template | 409 `template_limit_reached`, limit published in the response |
| Reformat while a regeneration runs | 409 `regeneration_in_progress` (existing) |
| Copy of a copy | allowed; `source_meeting_id` points at the immediate source |
| Copy whose worker dies | reaper clears the stage; page offers Try again / Delete |
| Transcript deleted on the source after a copy | copy keeps its own ciphertext |
| Transcript template on a non-diarized local transcript | speaker label = the single label; rewrite still runs |
| 3 h meeting, transcript template | ≈ 15 parts, cost shown; condense pass NOT used for the transcript sections (it would summarize) |
| Bulk delete containing the live recording | skipped `meeting_in_progress`; banner untouched |
| Move to the source space / to a system space / during reindex | skipped `same_space` / 404 / 409 `reindex_in_progress` |
| Move a `drive` or `meeting` document | skipped with its managed-by code; the row's action is not offered |
| Archive with a file missing on disk | zip carries the rest + `_missing.txt` |
| Archive over the size bound | 413 with the bound |
| Email with SMTP unreachable | 502 `email_send_failed`; auto-email logs `meeting_auto_email_skipped` |

## 5. Test plan (enriched during implementation, replayed at review)

**Backend unit** (`tests/unit/domains/meetings/`, `tests/unit/domains/rag_spaces/`): catalogue completeness ×6 and bounds; `TemplateRef` parsing; resolution precedence matrix (user / preference / auto / fallback / disabled); reformat replace/copy row shapes (no audio, no STT cost, transcript copied, SET NULL on source delete); reaper for stuck regeneration; transcript kind repair/render/`is_empty`; rewrite parts cut on turn boundaries, index validation, min-ratio retry; bulk delete classification; delivery through `EmailService` with `to_thread` and the `From` header; migration guard (upgrade/downgrade symmetry, data step); RAG move matrix, chunk relocation, rename failure revert, archive naming/missing/bound, download containment; prompt literal sync; metric coverage ratchet; file-size and CC ratchets; `test_markers`.

**Backend integration** (PostgreSQL): migration replay (`task db:migrate:replay-check`); `tests/agents/` suite — its trigger is « the runtime contract changed » (memory: this suite is outside the hook and `ci:fast`).

**Frontend** (vitest): library page (grouping, RowActions names en/fr, create/duplicate/edit/delete flows, limit reached); settings default-format select; reformat dialog (replace navigates nowhere, copy navigates to the new id, transcript warning); detail facts and pending panel; list selection + bulk delete + page step-back; template editor disclosure (collapsed by default, new section open, missing-instruction marker, keyboard); banner format select; header control / mobile menu entry (option D-1) with `dashboard-header-reachability`; spaces row actions, selection bar, move dialog, archive href; i18n parity ×6; `task test:frontend:coverage` thresholds; a11y / react-hooks / CC ratchets.

**Runtime proof** (dev containers, HTTP contract, the ADR-258 proof script extended): record → auto-selected template stored with reason → reformat copy with `transcript_clean` → copy READY, indexed, source keeps its minutes → email arrives with `From: APPLICATION_SMTP_FROM` (dev SMTP sink) → bulk delete of both → RAG projections gone; spaces: upload two files → archive → move one → retrieval finds it in the target space only.

## 6. Delivery lots (each gate-green before the next)

- **Lot A — bounded fixes**: A (SMTP), B (bulk delete), C (editor), D (surfaces per owner's choice, sticky banner).
- **Lot B — backend library**: migration, catalogue + i18n, template API, preferences, resolution, reformat/copy, transcript kind + rewrite, reaper, metrics, prompts.
- **Lot C — frontend library**: types/api/hooks, library page, settings, detail/list/banner/card, editor transcript kind, i18n ×6.
- **Lot D — knowledge spaces**: download, archive, move (+ optional bulk delete), row actions, selection bar, dialog.
- **Lot E — documentation and proof**: ADR-259, `MEETINGS.md`, `GUIDE_RAG_SPACES.md`, `.env.example`, `docs/INDEX.md` + `ADR_INDEX.md`, this spec linked from the ADR (doc audit: an unlinked living document is an orphan), runtime proof, `task ci:fast`.

## 7. Owner decisions (2026-09-03) — the design above is amended accordingly

1. **Recording surfaces: option 1, with the phone path the owner specified.** ≥ `lg`: the header toggle. < `lg`: the logo menu (`MobileNavMenu`) gains ONE dynamic entry, « Record a meeting » when idle and « Stop the recording » while live, and the logo trigger itself turns **red and pulses** while recording, with its accessible name stating the state (« Menu — recording in progress »). The sticky banner stays as the detailed status and the one-tap Stop. Consequence verified in the code: the header is rendered ABOVE `<main>`, where the provider is mounted today (`layout.tsx:277`), so `MeetingRecorderProvider` moves up to wrap the whole shell; the banner keeps its place through a `<MeetingRecorderBannerSlot/>` reading a private fine-grained context (the coarse public context stays what it is: the composer must not re-render at the level meter's cadence). `lib/mobile-visibility.ts` declares the new control as `substituted` below 1024 px by the menu entry; `e2e/smoke/dashboard-header-reachability.spec.ts` is re-run.
2. **Library: dedicated page.**
3. **Email subject: « {minutes_label} · {title} ».**
4. **No user has a customized template yet**: the migration carries no preference data step. Any `meeting_templates` row that exists simply joins the library under `custom`; `default_template_ref` starts `NULL` (automatic) for everyone.
5. **Transcript templates are excluded from automatic selection**; they are an explicit, a-posteriori choice (`auto_selectable=False`).
6. **Every reformat-as-new is indexed as its own document.** Vocabulary correction from the owner: it is never a « copy » — it is **a new set of minutes produced from the same transcript with another template**. The UI says « New minutes from this transcript » / « Replace these minutes », the link reads « From the same transcript as … », the API field stays `source_meeting_id`, the mode value becomes `new` (not `copy`). Not announced in the chat.
7. **All built-ins kept** (30 once assembled — the « 26 » of §E.3 was a mis-addition), the personality analyses included.
8. **Bulk delete of documents in spaces: included.**

## 8. Proofs

### 8.1 Executed 2026-09-03 (dev containers, HTTP contract driven by `proof_adr259.py`, audio = Windows speech voices Hortense/Paul, 50 s French dialogue, PCM 16 kHz in 2 segments)

| # | Step | Measured |
|---|---|---|
| 1 | Library | 30 built-ins in 7 categories (`analysis, business, learning, meeting, personal, technical, transcript`), `max_user_templates=50`; every transcript template `auto_selectable=false` |
| 2 | Templates CRUD | duplicate of `builtin:default_minutes` → `user:<uuid>` (201), PUT rename + 2 sections (200), GET, PUT on a built-in refused, DELETE 204 → GET 404 |
| 3 | Recording → READY | stop 202 → `normalizing → transcribing → synthesizing → ready` in **32 s**; engine `openai/gpt-4o-transcribe-diarize`, `fr`; **automatic selection** `builtin:it_project_meeting` (« Réunion de projet IT »), `selection=auto`, reason « L'échange porte clairement sur un point projet IT : migration de base, bascule DNS, certificat, gel des déploiements et risques. »; 7 sections; `total_cost_eur=0.00848`; 1 RAG document in « Réunions » |
| 4 | Reformat `new` (`builtin:transcript_clean`) | 202 with a new id and `source_meeting_id`; READY with its own report in **8 s**; **6 transcript lines**; `synthesis_cost_eur=0.0020`; list total 2, source `derived_count=1`; RAG documents 2 |
| 5 | Reformat `replace` (`builtin:daily_standup`) | 202 → `stage=synthesizing` on the READY row → new report in **4 s**, `template_selection=user` |
| 6 | Email | 200; the in-container SMTP sink (`ALERTMANAGER_SMTP_SMARTHOST=127.0.0.1:1025` for that run) received **envelope from `<lia@jeyswork.com>`** = `APPLICATION_SMTP_FROM`, `From: lia@jeyswork.com`, `To: proof-adr259@example.com`, `Subject: Compte rendu de réunion · Point projet : migration base, bascule DNS et certificat` |
| 7 | Bulk delete (both rows) | `{deleted: [2 ids], skipped: []}`; RAG documents in « Réunions » 2 → 0 |
| 8 | Spaces | two uploads (md, txt) → archive 292 bytes, members `['notes.md', 'plan.txt']`, `Content-Disposition` ASCII + RFC 5987; download names the original; move to space B `done=2 skipped=[]` and the files followed the rows (download from B = 200, space A empty); bulk-delete with a duplicated id → `done` = the two ids |

Not executed here: the chat question answered from the target space only (retrieval log), the Android/iOS shells, the header reachability e2e spec (Playwright is not run under Windows). Environment note: during the run the dev API container became a zombie the engine could not kill (recovery recorded in the program memory), so the proof ran after a Docker Desktop VM restart.

### 8.2 Owner review of the library (2026-09-03) and what changed

- The header shows the personality **icon alone at every width** (the title lives in the menu and the accessible name).
- The library page is **two sections** — « My templates » first (edit, duplicate, delete, batch delete), then the built-ins (preview, add to my templates, batch add) — each grouped by category, **every category folded by default**, empty categories absent, a category icon in the theme colour in front of every heading and title, the sections count as a themed badge. Adding never opens a form: the user shops among the built-ins and edits from « My templates ». A duplicated built-in kept its source category and was therefore lost among the built-ins — the reason the owner could not find their own templates.
- Backend: `POST /meetings/templates/bulk-duplicate` and `bulk-delete` (`{refs}` → done / skipped with a stable code, the cap respected per ref, a numbered name « (2) » when the user already owns the name); a batch delete that removes the preference's default template **resets it to automatic and says so** (`preference_reset`), which the UI surfaces as a notice.
- Shared primitives grew rather than being copied: `RowActions` and `SectionToolbar` take `blocked` (aria-disabled, focusable, still fires, the caller explains), `ui/selection-bar` serves both sections.

