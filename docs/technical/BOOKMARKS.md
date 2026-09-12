# Message bookmarks — the answers a person keeps (ADR-282)

An assistant answer lives in the ONE conversation that produced it, and that
conversation is reset often. A bookmark keeps an answer OUT of it: a copy taken
at the click — the answer, the request that produced it, the answer's date —
that survives the conversation and lives in the « Bookmarks » tab of « My
generated files ».

Decision record: [ADR-282](../architecture/ADR-282-Message-Bookmarks.md).

## What a bookmark is

| Column | Meaning |
|---|---|
| `user_id` | Whose bookmark. Every read filters on it. `CASCADE` on account deletion. |
| `message_id` | The archived assistant message, while it exists (`SET NULL`). With `user_id`, the toggle's identity — partial unique index. |
| `conversation_id` | The conversation, while it exists (`SET NULL`). |
| `content` | The answer, verbatim: markdown or a `lia-response` HTML document. |
| `request_content` | The person's last VISIBLE user message before the answer; `NULL` for a message LIA sent on its own initiative (`message_metadata.type` starts with `proactive_`). |
| `answered_at` | When the answer was written — the tab sorts on it. |

A conversation reset never touches a bookmark. Account deletion purges them
(`user_data_map`: `USER_PURGED`, export `FULL`).

## Backend — `apps/api/src/domains/bookmarks/`

| Module | Owns |
|---|---|
| `models.py` | `MessageBookmark`, the two indexes (listing order, toggle identity). |
| `queries.py` | `BookmarkFilters`, `build_bookmarks_statement(count=…)` — page and EXACT total from one `WHERE` (ADR-185), needle through `escape_like`, ordering ending on the primary key. |
| `repository.py` | The reads over the message table (declared `VISIBLE_ONLY` in `conversations/message_readers.py`) and the bookmark reads/writes. |
| `service.py` | `keep` (idempotent, four refusals), `list_page`, `attached_message_ids`, `remove`, `remove_by_message`. |
| `router.py` | `/bookmarks`: `POST` (guarded by the capability), `GET`, `GET /state`, `DELETE /{id}`, `DELETE /by-message/{message_id}`. |
| `errors.py` | `BookmarkLimitReachedError` (409) and the raisers, on the central taxonomy; sentences from `APIMessages`, six languages. |

Settings: `BOOKMARKS_ENABLED` (deployment ceiling of `PlatformCapability.BOOKMARKS`)
and `BOOKMARKS_MAX_PER_USER` (`core/config/bookmarks.py`, section `[96]` of the
`.env` files). Page bounds live in `core/constants.py`.

### What each route answers

- `POST /bookmarks {message_id}` → **201** with the bookmark; **200** when the
  message was already kept (the toggle asked for a state, not for a row);
  **404** for a message that is not the caller's, not the assistant's, or
  hidden (one answer for all three — saying « forbidden » would leak that the
  row exists); **400** for an answer with no text; **409** at the cap; **403**
  when the operator switched the capability off.
- `GET /bookmarks?q&limit&offset` → the page, `total` (exact), `limit`,
  `offset`, `max_limit`, `max_per_user` (ADR-184).
- `GET /bookmarks/state` → `{message_ids: {message_id: bookmark_id}}` for every
  bookmark still attached — one small payload for every bubble of the chat.
- `DELETE /bookmarks/{id}` → 204 / 404. `DELETE /bookmarks/by-message/{id}`
  → 204, or 404 when nothing was attached (the bubble reports what happened).

### The switch guards the act, never the record

`capability_dependencies(PlatformCapability.BOOKMARKS)` sits on the `POST`
route alone (`KEEP_GUARD`), the shape uploads took in ADR-279: switching the
act off must not close reading, exporting or deleting what was already kept.
`test_capability_route_wiring.py` reads the guard on the route.

## Frontend

| Piece | Path |
|---|---|
| Wire shapes (pinned to the schemas by a backend test) | `src/types/bookmarks.ts` |
| One state for the whole chat, optimistic toggle | `src/lib/bookmark-state-context.tsx` (`BookmarkStateProvider`, mounted around `ChatMessageList`; inert outside) |
| The bubble toggle, beside « copy » | `src/components/chat/BookmarkButton.tsx` (drawn on every archived answer with text — proactive notifications included — never on an active stream) |
| The tab | `src/components/settings/generated-assets/BookmarkList.tsx` + `BookmarkCard.tsx`, fourth tab of `GeneratedAssetsSettings` (reads `?tab=bookmarks` once, on arrival) |
| The `.md` export | `src/lib/bookmarks/markdown.ts` — the chat's path (`downloadMarkdown`, `messageToPlainText`), request quoted above the answer |
| The map node | `bookmarks`, counted, routed through `CAPABILITY_SECTION_TAB` (the section belongs to `generated_files`) |

The instance publishes `features.bookmarks_enabled` in `/config`; the operator's
runtime switch answers 403 on the act, which the bubble shows as the server's
own sentence.

## Tests

- Unit: `tests/unit/domains/bookmarks/` (queries, service, router, wire-shape
  parity) plus the guards that refused during the lot (capability coverage and
  wiring, capability map, data map, message readers).
- Integration on PostgreSQL: `tests/integration/domains/bookmarks/` — SET NULL
  on conversation delete, CASCADE on account delete, the partial unique index,
  the visible-only reads, the listing and its search.
- Frontend: `BookmarkButton.test.tsx` (state read once, optimistic toggle and
  rollback, double-click guard, accessible names), `BookmarkList.test.tsx`
  (exact total against the cap, empty states, card actions),
  `GeneratedAssetsSettings.test.tsx` (the conditional tab, `?tab=`),
  `markdown.test.ts`.
- Browser: `e2e/smoke/message-bookmarks.spec.ts` — keep and let go from the
  bubble, a detached bookmark whole in its tab, no card past 320 px.
