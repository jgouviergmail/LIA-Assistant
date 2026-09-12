# Message bookmarks — design

**Date:** 2026-09-12 · **Status:** approved by the owner (chat, 2026-09-12) · **ADR:** ADR-282

## Need

A person must be able to KEEP some of the assistant's answers even after the
conversation that produced them is deleted. On every assistant bubble, next to
« copy », a bookmark icon keeps the message; the kept messages live in a new
« Bookmarks » tab of « Mes fichiers générés ». Each bookmark is dated and
attached to the request that produced it. It can be deleted, shared and
downloaded as Markdown (what the chat already offers), and its formatting is
rendered faithfully.

Owner decisions taken in the design conversation:

- the bubble icon is a **toggle** (filled when kept, second click removes);
- the `.md` export carries the request as a quotation above the answer;
- the tab sorts by the answer's date, newest first.

## Approach

**Copy plus optional reference.** A bookmark COPIES the answer and the request
at the instant of the click, and keeps `message_id` / `conversation_id` in
`ON DELETE SET NULL`: while the conversation lives the bubble knows its state;
when it dies the bookmark stays whole. Rejected: a pointer alone (dies with the
conversation), and a `.md` attachment in the ADR-279 gallery (24 h TTL, disk
storage, and « rendered faithfully » would mean re-parsing a file).

## Backend — `domains/bookmarks/`

- **Table `message_bookmarks`**: `id`, `user_id` (CASCADE), `message_id`,
  `conversation_id` (both SET NULL), `content` (the answer, markdown or a
  `lia-response` HTML document, verbatim), `request_content` (the person's
  words, or `NULL` when no visible user message precedes the answer — a
  proactive notification), `answered_at` (the answer's `created_at`),
  `created_at` / `updated_at` (mixin). Partial unique index on
  `(user_id, message_id) WHERE message_id IS NOT NULL` — the toggle is
  idempotent by construction. Index on `(user_id, answered_at DESC, id)`.
- **The request is resolved SERVER-SIDE**: the bookmarks repository owns two
  reads under `visible_only` — the assistant message the caller owns, and the
  last VISIBLE user message before it — and declares itself `VISIBLE_ONLY` in
  `conversations/message_readers.py` (the conversations repository is
  size-frozen; the doctrine provides for exactly this case).
- **Routes** (`/bookmarks`, wired under `BOOKMARKS_ENABLED`):
  - `POST` `{message_id}` → 201 with the bookmark (200 when it already
    existed: the toggle asked for a state, not for a row). Refuses a message
    that is not the caller's, not the assistant's, hidden, or empty. Refuses
    beyond `BOOKMARKS_MAX_PER_USER` (409, translated, six languages).
  - `GET` `?q&limit&offset` → page, EXACT total, `limit`, `offset`,
    `max_limit`, `max_per_user` (ADR-184/185). Sort `answered_at DESC, id`.
  - `GET /state` → `{message_ids: {message_id: bookmark_id}}` for every
    bookmark still attached to a message (bounded by the cap).
  - `DELETE /{id}` → 204; a foreign or unknown id is 404 with
    `hide_existence` semantics.
  - `DELETE /by-message/{message_id}` → 204 (the bubble's second click).
- **Capability** `PlatformCapability.BOOKMARKS` (family `knowledge`, ceiling
  `bookmarks_enabled`, `route_enforced`): the guard sits on the **write that
  creates** (`POST`) only — listing, exporting and deleting stay open
  (ADR-279: a switch removes the capability, never the record).
- **Map node** `bookmarks` (counted, capability BOOKMARKS) pointing at the
  `generated-assets` section.
- **Data lifecycle**: `user_data_map` → `USER_PURGED` + export `FULL`;
  `build_purge_statements` → `by_user("message_bookmarks")`. A conversation
  reset never touches bookmarks (that is the point).

## Frontend

- **Bubble**: `BookmarkButton` next to « copy », drawn on every archived
  assistant bubble with text (proactive notifications included, never an
  active stream) when the instance publishes `features.bookmarks_enabled`. State comes from ONE
  `BookmarkStateProvider` mounted around the chat (one `GET /bookmarks/state`
  per mount), optimistic toggle, toasts on success and on refusal (cap, or the
  operator's switch).
- **Tab**: fourth family « Bookmarks » in `GeneratedAssetsSettings`
  (`grid-cols-4`), `BookmarkList` + `BookmarkCard`: answer date, request as a
  quotation (clamped, expandable), answer rendered by `MarkdownContent`
  (markdown AND `lia-response` HTML), actions share (`navigator.share`,
  feature detection), download `.md` (client-side, `downloadMarkdown` +
  `messageToPlainText`, the chat's own path), delete (confirm). Search needle,
  exact total, pagination — the three galleries' shape.
- i18n in six languages; `useAppConfig.features.bookmarks_enabled`.

## Tests

Unit (queries, service, router, guards: capability coverage and wiring, data
map, message readers, frontend wire-shape parity), integration on PostgreSQL
(partial unique, SET NULL on conversation delete, account purge, cap), vitest
(button toggle, tab, card actions), one hermetic Playwright journey (bookmark
from a bubble → the tab lists it → delete).
