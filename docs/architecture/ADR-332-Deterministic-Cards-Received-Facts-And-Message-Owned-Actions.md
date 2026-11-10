# ADR-332 — Deterministic cards: received facts shown whole, actions owned by their message

**Status:** Accepted — 2026-10-04 (HTML cards modernisation, `cc20233a`, merged in
`b9495566`; CI follow-up `b1065e50`).

**Amends:** ADR-289 (one description, several surfaces — now for data cards too),
ADR-286 (what reaches the model is a projection, never the card), ADR-272 (a browser
map is a platform spend, admitted and recorded per account), ADR-185 (no figure
nobody measured), ADR-316 (a third party's words are quoted literally).

**Reference:** [docs/technical/HTML_CARDS.md](../technical/HTML_CARDS.md).

## Context

An answer that carries data (e-mails, events, contacts, places, routes, weather,
research, tickets, MCP results…) is rendered by the server as HTML cards, archived
with the message and re-rendered by the chat through a sanitiser. Before this change,
measured on the real producers:

1. **Received facts were lost on the way.** A card showed what its renderer happened
   to read: a contact's second organisation, a calendar's visible alias, a task's
   subtasks, a route's alternatives, a place's opening periods were received, paid
   for, and never drawn. Absence, zero and `false` were often the same blank.
2. **The display leaked into the model.** A probe on the real e-mail producer showed
   a body withheld under `detail=metadata` reaching the next ReAct turn through the
   card's HTML, which the history kept verbatim. The boundary "display-only" was not
   guaranteed by the registry alone.
3. **A card could not act safely.** Reply, forward or adjusting a reminder from a card
   needs a target. A global registry where the last writer wins can repaint an old
   card with a newer item of the same id, and an HTML class or `data-action` written
   by external text must never authorise anything.
4. **A map in the browser is a paid call.** Interactive route maps load Google's Maps
   JavaScript SDK on a key the browser necessarily sees.

## Decision

### 1. The server keeps rendering; the browser only enhances

Rendering stays deterministic and server-side (one renderer, independent of the model
and of the execution mode). Typed presentation adapters per family resolve provider
aliases, units and optional values into shared primitives (title, full text, facts,
disclosures); a small React layer adds what HTML cannot do (gallery, lightbox,
time-slot selection, composition). An archived answer opened again goes through the
same sanitiser and the same enhancements; without them it stays readable.

### 2. A received fact is shown whole, and never invented

Missing, zero and `false` are three states. A renderer does not infer a fact from an
absence, fabricate a default time, collapse a zero cost or use a provider identifier as
a human name. Complete received prose stays reachable behind a native disclosure
rather than silently cut. Source clocks go through ONE parser (`core/time_parsing.py`):
an explicit offset is authoritative, an unknown zone is never read as UTC, an all-day
date stays a civil date. Microsoft's native recurrence stays a native fact rather than
a lossy invented RRULE. This is a policy for what was **received**: no list endpoint
requests more fields, and opening a disclosure calls no provider, no model, no tool.

### 3. The model reads a semantic view, never the card

The assistant message carries a versioned semantic view of what the person was shown
(`display/model_history.py`); every later provider, history and compaction path reads
it through `infrastructure/llm/message_view.py`. Card HTML, images, private action
context and display-only trees never become recurring prompt content; authorised
facts keep their trust wrapper. A presentation change therefore buys no synthesis call
and no prompt growth.

### 4. An action belongs to the message that displayed its source

A composition affordance is selected by the server and bound to the assistant answer
that showed the source (`display/card_actions.py`). At click time
`card_composition_service.py` re-reads that answer — owned by the account, in the
current conversation, from its run — and the canonical source with its account grant.
Reply, forward, email deletion or a reminder adjustment PREPARES a request or a draft; nothing is sent
or executed by the click, and HITL, modification, resume and retries re-check the same
binding. A source whose account or mailbox cannot be bound structurally offers no
action (Apple Mail today: an IMAP uid carries no mailbox scope in the contract). The
model receives a versioned directive (`card_composition_context.txt`) naming the
verified target, never an instruction extracted from card HTML.

### 5. A browser map is admitted, budgeted and recorded

A route card can open an interactive map of the provider's exact geometry; selecting
an alternative never recomputes an itinerary. Activation is explicit and shows its
estimated unit cost first. The SDK key (`GOOGLE_API_KEY`, or the optional
`GOOGLE_MAPS_BROWSER_API_KEY`) is released only through authenticated admission under
the account and instance ceilings and a per-user rate limit, then bound by a
short-lived signed grant; each construction is recorded on the existing ledgers under
one durable run, with no schema change. The feature stays off until the
`maps_javascript` price exists in the catalogue: the seed declares it for a fresh
install, and migration `ef46f93d7745` adds it to an upgraded one, which never replays
the seed (it was missing there until 2026-10-04). What this records is the
browser-observed map construction, not Google's invoice: the key must also be
restricted and quota-capped in the Cloud console.

### 6. One material for overlays

Dialogs, menus, selects, tooltips, viewers and notifications share one glass material
(`lia-overlays.css`) built on the theme tokens; reduced transparency and forced colours
restore an opaque surface, reduced motion removes decorative transitions, and a manual
modal returns focus to the control that opened it.

## Consequences

- Every domain renderer is tested from its real producer through registry
  serialisation (`tests/helpers/card_reference_cases.py` generates the corpus the
  frontend and browser tests read; a test refuses drift), with explicit zero, false,
  empty, non-finite and hostile inputs.
- External text is escaped once (`display/escaping.py`), URLs validated, the chat
  sanitiser keeps an exact allowlist; MCP snapshots are bounded and credential-named
  fields redacted (`core/credential_fields.py`), which does not claim to detect a
  secret written in free prose.
- Media galleries load the visible image only, on the authorised proxy path, behind
  the shared admission.
- Limits stated, not hidden: a killed browser can lose a map report; a public SDK key
  cannot enforce LIA's per-account limits at Google; Apple Mail cards offer no action.

## Amendment — 2026-11-07: Enveloppes and the received-address map

The selected Enveloppes direction changes each family's composition without replacing
the deterministic rendering and message-owned interaction architecture. Email uses
an envelope, events an invitation, files a folder, articles a reading spread and
research a source-bearing brief. MCP results and execution results have a receipt
form; a proposal remains visibly distinct from an explicit outcome. The stylesheet
owners and family mapping are documented in
[HTML_CARDS.md](../technical/HTML_CARDS.md#enveloppes-compositions-and-collection-density):
[craft](../../apps/web/src/styles/lia-cards-craft.css),
[people](../../apps/web/src/styles/lia-cards-people.css),
[world](../../apps/web/src/styles/lia-cards-world.css),
[knowledge](../../apps/web/src/styles/lia-cards-knowledge.css) and
[location](../../apps/web/src/styles/lia-cards-location.css).

1. **One theme and one responsive UI.** Materials derive from the account's existing
   palette and the application's light/dark/OLED tokens. Body text retains the
   account's text scaling; the craft layer owns editorial headings. The phone
   recomposes the same cards and specialized React modules at their container width,
   not a second native UI or a reduced payload.
2. **A fold changes density, never the selected set.** The initial email slice and
   invitation participant slice are declared by `HTML_EMAIL_VISIBLE_MESSAGES` and
   `HTML_EVENT_VISIBLE_PARTICIPANTS` in
   [core/constants.py](../../apps/api/src/core/constants.py). The
   [collection renderer](../../apps/api/src/domains/agents/display/card_collection.py)
   and [event presentation](../../apps/api/src/domains/agents/display/components/event_presentation.py)
   retain every remaining received entry behind a native disclosure with an exact
   remainder. Revealing stored text needs no provider or model request. The existing
   answer-level fold and lazy media lifecycle remain separate.
3. **Illustration cannot replace evidence.** Actual supplied thumbnails, photos,
   map/Street View previews, forecast slots and generated-format excerpts keep their
   existing renderers, links, attribution and controls. A missing RSVP or lamp state
   does not become a positive or negative fact. Generated-file lifetime checks,
   HITL targets and confirmation rules, and MCP redaction and display bounds remain
   authoritative; a visible MCP limit notice is not hidden inside its closed result.
4. **An address can use the existing admitted map.** A LOCATION card emits a bounded,
   typed [location projection](../../apps/api/src/domains/agents/display/components/location_map.py)
   from received finite coordinates, revalidated by the
   [browser decoder](../../apps/web/src/lib/location-map-data.ts). The
   [enhancement](../../apps/web/src/components/chat/markdown-location-map.tsx) keeps the
   static fallback and uses the existing paid-map admission, shared controller and
   reporting lifecycle after explicit cost-disclosed activation. Its marker shows
   the supplied address and source link in the shared desktop/phone popup. It neither
   creates a PLACE registry entity nor requests geocoding, GPS, Places details or a
   route. Invalid or unavailable enhancement paths leave the original card readable.

The [existing qualification boundaries](../technical/HTML_CARDS.md#regression-strategy-and-operational-limits)
still apply: regenerated backend/browser fixtures, source-fact and action parity,
responsive reflow, keyboard/focus, theme/contrast and media lifecycle checks are
required for the implementation. This amendment records the architecture and
behavior; it does not claim completed test runs, production deployment or physical
WebView qualification.
