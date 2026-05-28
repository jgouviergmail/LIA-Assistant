# Conversation History Pagination — Technical Reference

**Status**: Implemented (2026-05-29) — v1.20.14.

This document covers the keyset (scroll-up) pagination on
`GET /conversations/me/messages` and the UI wiring that consumes it. The endpoint
serves the chat-page history rendering; it is **independent** of the LangGraph
checkpoint and of the conversation compaction layer
([COMPACTION_v2.md](COMPACTION_v2.md)) — those operate on the in-context
message window, not on the persistent `conversation_messages` table.

---

## 1. Why this exists

Before v1.20.14 the endpoint returned **the 50 newest messages, full stop** —
hard-coded default, hard cap at 200, no cursor, no scroll-back. For
conversations that accumulated to multi-million-token scale (typical for
long-running daily-assistant usage), the **start of the conversation was
unreachable from the UI** even though every message was preserved in the
`conversation_messages` table.

Two confusions to dispel up front:

- **Compaction does not delete messages.** Compaction v2 rewrites the in-context
  window of the LangGraph checkpoint to keep prompts under the model's context
  budget. The persistent `conversation_messages` rows are untouched.
- **The only delete path is conversation reset.** `POST /conversations/me/reset`
  cascade-deletes the entire conversation and its messages. Nothing else
  removes rows.

So the underlying data was always there — pagination simply exposes it.

---

## 2. API contract

`GET /conversations/me/messages`

| Param | Type | Default | Bounds | Notes |
|---|---|---|---|---|
| `limit` | int | `settings.conversation_history_default_limit` | `ge=1, le=settings.conversation_history_max_limit` | Defaults sourced from env (see §5). |
| `search` | str \| null | `null` | `2 ≤ len ≤ 200` | Case-insensitive `ILIKE` on `content`. Accent-sensitive (MVP). |
| `before` | datetime \| null | `null` | ISO-8601 | Keyset cursor — only messages strictly older than this are returned. |

Response (`ConversationMessagesResponse`):

```jsonc
{
  "messages": [/* ConversationMessageResponse, newest first */],
  "conversation_id": "…",
  "total_count": 12,           // user-message count in THIS PAGE (legacy field)
  "has_more": true,            // older messages remain beyond this page
  "next_cursor": "2026-05-15T08:14:22.123456+00:00"  // null when has_more=false
}
```

Pagination contract:

- **First page**: omit `before`. Returns the newest `limit` messages.
- **Older pages**: pass the previous response's `next_cursor` as `before`.
- **End of history**: `has_more=false` and `next_cursor=null`.

`total_count` is **the user-message count in the returned page only**, not a
global total. Kept for backwards compatibility — clients that need the global
total must aggregate across paginated requests (or use `/conversations/me/totals`
for token/cost aggregates).

---

## 3. Backend — keyset pagination

### Why keyset and not offset

The codebase convention elsewhere is offset-based pagination returning
`tuple[list[T], int]`. Conversation history deliberately uses **keyset
(cursor) pagination** instead:

- A global `COUNT(*)` would be `O(conversation_messages)` per request — no
  cheap filter can short-circuit it — and is useless to the scroll-up UI,
  which only needs `has_more`.
- Keyset uses the composite index `ix_conversation_messages_conv_created
  (conversation_id, created_at DESC)` for an index-only seek per page,
  regardless of conversation length.

The choice is documented in
`ConversationRepository.get_messages_with_token_summaries` so future readers
don't try to "align" it back to the offset pattern.

### `has_more` without a second query

The router asks the service for `limit + 1` rows. If `limit + 1` are
returned, older messages exist beyond the current page: the router truncates
the response to `limit`, sets `has_more=true`, and returns the `created_at`
of the oldest row in the truncated slice as `next_cursor`. Otherwise
`has_more=false` and `next_cursor=null`.

### Cursor precision

`before_created_at` is applied as a strict `<` filter on `created_at`
(microsecond-precision Postgres timestamp). The collision window for a
strict `<` cursor is sub-microsecond — negligible in practice. If a
collision is ever observed, upgrade to a composite `(created_at, id)` cursor.
The repository docstring carries a `TODO` to that effect.

### Combined with `search`

`before` and `search` AND-compose: the keyset filter narrows by time, the
`ILIKE` filter narrows by content. A pagination test covers this combination
(`test_cursor_combined_with_search`).

---

## 4. Frontend — scroll-up wiring

### Hook (`useConversation`)

Three pagination surfaces:

- `loadConversationPage()` — first page, returns
  `{messages, hasMore, nextCursor}`.
- `loadOlderMessages(cursor)` — next older page. **Mutex-guarded** by a ref:
  overlapping calls (fast scroll) return an empty page immediately without
  hitting the network.
- `isLoadingOlder` — booleen state for UI loaders.

`fetchPage(before?)` is the shared internal helper that owns the API call,
DESC→display reverse, and `toUiMessage` mapping.

### List component (`ChatMessageList`)

Three new props: `hasMoreOlder`, `isLoadingOlder`, `onLoadOlder`.

A 1-px sentinel is rendered above the first message when `hasMoreOlder` is
true. An `IntersectionObserver` is bound on the scroll container with
`rootMargin: 200px 0 0 0` — `onLoadOlder` fires as soon as the user gets
within 200 px of the top.

**Scroll-position preservation.** Without intervention, prepending older
messages would push the existing list down and the viewport would visibly
jump. Two cooperating effects keep the viewport anchored exactly where the
user was reading:

1. `prevScrollHeightRef` is captured right before `onLoadOlder()` fires.
2. After React commits the new messages, a `useLayoutEffect` detects the
   prepend (`messages[0].id` changed) and offsets `container.scrollTop` by
   the new content height (`scrollHeight - prevScrollHeight`). It also
   raises `wasPrependRef`.
3. The pre-existing auto-scroll-to-bottom `useEffect` reads `wasPrependRef`
   in the same render cycle and **skips its `scrollIntoView`** when raised,
   then lowers the flag.

Without step 3 the auto-scroll-to-bottom would undo step 2 and the viewport
would snap to the bottom of the list, hiding the freshly loaded older
messages. The flag is consumed exactly once per prepend.

### Page-level handler (`chat/page.tsx`)

Owns the `oldestCursor` / `hasMoreOlder` state. `handleLoadOlder()`:

1. Skips if no cursor or `hasMoreOlder` is already false.
2. Calls `loadOlderMessages(oldestCursor)`.
3. **Dedup by id** before prepending — necessary because the cursor window
   can overlap if a new message lands during the fetch and shifts the page
   boundary.
4. Updates `hasMoreOlder` and `oldestCursor` from the response. Even an
   empty page must commit `hasMore=false` so the sentinel stops firing — a
   sentinel-loop guard.

The sentinel is **suppressed while the in-chat search is active**
(`hasMoreOlder={hasMoreOlder && !searchQuery}`). The search filter runs
client-side over already-loaded messages, so a sentinel during search would
conflate *"no match in this loaded page"* with *"no match in remote history"*.

### Pagination state reset paths

Whenever the message list is fully replaced — initial mount, return from
background (`visibilitychange`), post-scheduled-action refresh, conversation
reset — `oldestCursor` and `hasMoreOlder` are re-committed from the new page
(or zeroed on reset). Otherwise the cursor would point into a no-longer-
visible region of the list and the sentinel would behave erratically.

---

## 5. Configuration

| Env var | Setting | Default | Range |
|---|---|---|---|
| `CONVERSATION_HISTORY_DEFAULT_LIMIT` | `settings.conversation_history_default_limit` | `50` | `1–1000` |
| `CONVERSATION_HISTORY_MAX_LIMIT` | `settings.conversation_history_max_limit` | `200` | `1–1000` |

Both are surfaced in `.env.example` / `.env.prod.example`. Raising
`DEFAULT_LIMIT` increases the first-page payload (heavier load but fewer
scroll-up round-trips); raising `MAX_LIMIT` widens the hard cap on the
`limit` query param. The backend cap protects the database and JSON payload
size; the frontend constant (`CONVERSATION_PAGE_SIZE` in
`useConversation.ts`) should stay aligned with `DEFAULT_LIMIT` but an
overshoot is harmless (capped server-side).

---

## 6. Tests

| File | Coverage |
|---|---|
| `apps/api/tests/unit/domains/conversations/test_messages_pagination.py` | Router unit tests (mocked service): `has_more=true` truncation, `has_more=false` short page, `limit+1` request contract, `before` forwarding. Repo integration tests (real Postgres): no-cursor returns newest-first, cursor returns strictly-older, `before+search` AND-composition. |
| `apps/web/src/hooks/__tests__/useConversation.pagination.test.ts` | Hook unit tests (mocked `apiClient`): page returned in display order with pagination metadata, `before` forwarded, mutex skips overlapping calls (only one network call), first page omits `before`. |

---

## 7. Future work

- **Composite cursor.** Upgrade `before` to `(created_at, id)` keyset if
  microsecond collisions ever appear in prod.
- **Search server-side.** Currently search is client-side only over loaded
  messages — the sentinel is therefore disabled during search. Server-side
  search would let scroll-up follow search hits across the full history.
- **Global message count.** If `total_count`'s page-only semantics become a
  burden, expose a separate `/conversations/me/stats` aggregate computed
  via `COUNT(*)` once, cached, and refreshed on writes.
