# Phone ingestion and Mes SMS

[Decision](../architecture/ADR-357-Phone-Ingestion-And-Personal-SMS-Archive.md) ·
[User guide](../guides/GUIDE_IPHONE_SHORTCUTS_SMS.md) ·
[Recovery](../runbooks/SMS_INGESTION_RECOVERY.md) ·
[Qualification](SMS_QUALIFICATION.md)

## Source ownership

| Responsibility | Authority |
|---|---|
| Resource policies, principals, receipts, token lifecycle, delivery leases | [ingestion](../../apps/api/src/domains/ingestion/) |
| Strict SMS wire contract and atomic ingestion | [schemas](../../apps/api/src/domains/sms/schemas.py), [ingestion service](../../apps/api/src/domains/sms/ingestion.py) |
| Shared read/consent gate and sender resolution | [reads](../../apps/api/src/domains/sms/reads.py), [facade](../../apps/api/src/domains/sms/facade.py) |
| Limits and prompt budgets | [IngestionSettings](../../apps/api/src/core/config/ingestion.py) |
| Management approval and original-browser secret | [application commands](../../apps/api/src/domains/agents/application/sms_ui_commands.py) |
| Personal data lifecycle | [table map](../../apps/api/src/domains/users/user_data_map.py), [user columns](../../apps/api/src/domains/users/user_column_map.py), [export](../../apps/api/src/domains/account_export/) |
| Assistant proof, state filtering, projection and cards | [agents/SMS](../../apps/api/src/domains/agents/sms/) |
| Exact home counts, bounded personal previews and separate model evidence | [summary](../../apps/api/src/domains/sms/summary.py), [briefing source](../../apps/api/src/domains/briefing/sms_context.py) |
| Proactive eligibility and mention bookkeeping | [heartbeat source](../../apps/api/src/domains/heartbeat/sms_context.py), [mention writer](../../apps/api/src/domains/sms/proactive.py) |
| Explicit Radio source and spoken phone/Live adapter | [Radio reader](../../apps/api/src/domains/radio/sms_context.py), [spoken reader](../../apps/api/src/domains/agents/telephony/sms_output.py), [phone catalogue](../../apps/api/src/domains/agents/telephony/live_specs.py) |
| Content-free reception push | [delivery worker](../../apps/api/src/infrastructure/scheduler/ingestion_delivery.py) |

## End-to-end contract

~~~mermaid
flowchart TD
    P[Shortcuts HTTPS POST] --> A[Owner, source, token and admission]
    A --> T[Receipt + encrypted SMS + index + outbox transaction]
    T --> D[Leased content-free delivery]
    T --> R[Authenticated SMS reading and exact counts]
    R --> X[Bounded external assistant evidence]
    R --> E[Streaming personal export]
    X --> F[Fresh owner, consent and source check]
~~~

POST /api/v1/ingest/message uses Authorization: Bearer, not a session cookie. The compact wire fields are sender, date, body and o; event_id, schema_version and date_kind make retry and time provenance explicit. See the [wire model](../../apps/api/src/domains/sms/schemas.py) rather than duplicating its limits here.

Use an aware ISO 8601 string. Preserve text, normalize the instant to UTC and reject unsupported versions, invalid text, unknown fields or an excessively future timestamp. Shortcuts' capture time must be labelled captured; omission remains unknown.

A stable event UUID identifies one source event. The same event and payload is duplicate; different content under that identifier is conflict. Without an event UUID, the canonical payload digest is the identity. Changing the event identifier, timestamp or source can represent another event: this is not semantic cross-device deduplication.

Single-item responses distinguish stored, duplicate/ignored, conflict and invalid outcomes. A batch carries per-item verdicts; a successful HTTP response alone does not prove that every item was stored. A storage failure may leave commit acknowledgement unknown: retry the identical event, never invent a new identifier to get around it. Admission depends on Redis; unavailable admission fails before a write.

## Data, authority and privacy

Bodies and senders are encrypted at rest. Stable tenant HMAC material is wrapped separately from write credentials. The blind index supports bounded lexical search with exact verification after decryption; it is not an embedding index. Ambiguous broad searches ask for narrower criteria instead of claiming no match.

Receipts, credential hashes and index terms are operational, not plaintext export records. Erasure removes content/index/deliveries and keeps content-free replay tombstones. Receipt and retained-message limits are distinct; logical SMS bytes are not a physical PostgreSQL disk cap. A retry with the same source/event and payload cannot resurrect an erased SMS; without an event identifier the full canonical payload must remain identical. A new event identifier, another source or a changed payload without an identifier may represent a new event.

Confirmed source mutations take the owner lock before credentials and source state. Provider contact IO runs outside the SQL fence, followed by fresh publication checks. Each concurrent source fetch uses its own session. Pending, leased, sent, cancelled and uncertain deliveries are not interchangeable; see the [uncertain-delivery runbook](../runbooks/alerts/PhoneIngestionDeliveryUncertain.md).

The SMS filter excludes recognized OTPs, passwords/access/recovery secrets, identifiable sign-in/reset links and blocked senders before storage. It cannot recognize every sensitive free-text message. No ingestion-triggered model or automatic memory extraction is added.

Assistant consent permits necessary excerpts to reach the configured model. Existing platform/BYOK quotas, pricing and LLM tracing policies still apply. SMS technical logs and metrics carry content-free codes and bounded labels, not the sender, body, raw credential or search text.

## Application integration

Settings place Mes SMS after Meetings. As in Health Metrics, statistics open on arrival; ingestion setup, assistant preferences, blocked senders and bulk deletion fold closed. Reading lives directly below statistics in its own initially open disclosure at `/dashboard/settings?section=sms`. Existing `/dashboard/sms` links redirect there and preserve the focused message identifier. Focused text is withdrawn before rereading on SMS invalidation; subsequent refreshes preserve keyboard focus. The three preference switches save directly through session-only `PATCH /sms/preferences`, one strict boolean field per request. They share the command writer's owner fence, delivery cancellation and consent invalidation without creating an approval draft. SMS reading has descending day and sender views, account-timezone grouping, bounded pagination, literal text and read-only content; block/bulk-delete/token actions use the approval UI. Contacts and relations are best-effort identity evidence, not verification of who sent a message.

SMS reading initially selects **By sender**. A red icon below a message's date deletes that one message without a confirmation dialog. Its explicit browser click reuses the existing command preparation/confirmation transaction, accepting only the same single ID, no sender/date/all scope and at most one affected row. It retains owner lifetime, expiry, duplicate-click and uncertain-acknowledgement guards; agent commands and bulk deletion still present their approval UI. Search results do not silently narrow a sender-wide deletion. Day scopes use two civil midnights, including daylight-saving transitions. The bulk dialog stays open while confirmation is pending and a removed direct-action trigger restores focus to a surviving disclosure. The visible capture-time disclaimer is omitted; source timestamp provenance remains in the data and assistant contracts. The interface calls these retained messages SMS, with no separate archived state.

Relationships expose exact SMS totals and a bounded list, immediately above exchanged provider emails on both desktop and mobile. Explicitly SMS-derived debriefs are invalidated when their source changes; SMS does not silently expand an existing debrief scope or become a portrait source.

The home card shows exact SMS counts and the latest retained messages as bounded personal previews, using the same row primitive as Mails. `BRIEFING_MAX_SMS_ITEMS` controls their number; its default and bounds live in [BriefingSettings](../../apps/api/src/core/config/briefing.py). Selection spans all retained messages, in descending source-date order, independently of the recent-count window. Each row opens its message directly in SMS settings; there is no additional section footer link. Display uses the account timezone and preserves captured/unknown timestamp provenance.

These personal previews do not require assistant consent and never become implicit model evidence. Other aggregation readers retain the metadata projection. The card uses the shared owner/capability gate and batched identity resolver, rechecks source proof after directory lookup and before publishing a completed bundle, and has no source cache or last-good fallback. Authenticated briefing responses prohibit HTTP caching. Browser invalidation immediately masks previews until a fresh read succeeds, including when an older initial read is still in flight.

Greeting/synthesis use only separately authorized bounded evidence; source changes after an awaited profile lookup prevent a paid SMS call, and changes during the model call suppress its text while retaining spent usage. SMS invalidation cancels in-flight home text, leaving regeneration to an explicit user action.

Both assistant modes use the same read-only list/search/get tools, strict schemas, proof, external-content envelope and native card. Long bodies continue at returned code-point offsets. Missing, stale, withdrawn or cross-owner proof fails closed at model boundaries and context re-serving. Ordinary non-SMS reference rendering retains its established output.

Immediate reception pushes follow the dedicated SMS toggle, unfolded at the head of Settings › My SMS, at any hour and contain no message text. The in-app notice shows the sender in bold and the message: it reads both through the session-only archive read once the content-free signal arrives, and announces the arrival alone when that read fails. Proactive useful-fact notifications use the heartbeat's own source switch, quiet windows and quotas. They require actionable offered IDs, not a receipt/unread claim; only successfully surfaced IDs receive mention metadata. A notification written with SMS in view is delivered, remembered and read back by the next decision like one drawn from mail ([ADR-357 amendment 2026-10-23](../architecture/ADR-357-Phone-Ingestion-And-Personal-SMS-Archive.md)).

Radio offers SMS as an explicit personal source in its settings. It reads the consented SMS source directly, under the shared identity timeout and a projection bounded by the receiving writer/verifier slots and the SMS context budget. Its fact limit lives in [personal.py](../../apps/api/src/domains/radio/personal.py). SMS belongs to the journal's day material, remains sensitive, and is excluded in company, when its source is disabled or when the personal journal is off. Source proofs travel privately with the facts, outside serialized prompt data, and are revalidated before model work, before speech production and after awaited production. Withdrawal suppresses publication while retaining already spent usage. No ingestion-triggered model call is added.

The owner's phone and shared direct-Live host expose the same read-only source through the native `list_sms_tool` adapter. The catalogue's required request object is unsuitable for spoken flat parameters: the adapter validates spoken sender/date/search filters with the existing SMS request schemas, then reuses `SmsToolReader`, source authority and the normal voice external-content/token projection. Capability hiding, the SMS feature flag, assistant consent and the owner's disabled phone domains all apply. The phone settings panel exposes this source under an inset accessible heading. No SMS mutation is offered through the spoken adapter.

An SMS in view is personal data like a mail: proactive content it informed has no private mode of its own (ADR-357 amendment 2026-10-23). Its push shows the words, external channels receive it, Radio may come back to it, continuity memory stores it and the next decision window reads it — the anti-repetition guard depends on that last point. Only the reception push stays content-free. The separately authorized direct Radio/phone/Live readers above grant no unrelated peer/routine access.

## Lifecycle and extension

Personal export includes readable SMS and user-owned metadata in bounded streams; encrypted internals and HMAC/search material are excluded. The structured JSON preserves source text; the readable Markdown quotes it literally so supplied HTML, image or formatting syntax cannot become active content. Hosted archives become unavailable after a source erasure that invalidates their snapshot. A downloaded copy, an earlier chat/phone answer, already delivered Radio audio or a memory retained under the existing conversation preferences is not recalled by deleting the source SMS.

For another phone resource, add a strict resource contract and policy, reuse authority/admission/receipts/delivery where semantics agree, and declare its own models, purges/exports, readers, feature/consultation/action registries and UI. Do not bypass server approval or let a new catalogue entry grant unrelated surfaces access automatically.
