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
| Exact home counts versus model evidence | [summary](../../apps/api/src/domains/sms/summary.py), [briefing source](../../apps/api/src/domains/briefing/sms_context.py) |
| Proactive eligibility and mention bookkeeping | [heartbeat source](../../apps/api/src/domains/heartbeat/sms_context.py), [mention writer](../../apps/api/src/domains/sms/proactive.py) |
| Private notification transport | [privacy policy](../../apps/api/src/core/notification_privacy.py), [dispatcher](../../apps/api/src/infrastructure/proactive/notification.py) |

## End-to-end contract

~~~mermaid
flowchart TD
    P[Shortcuts HTTPS POST] --> A[Owner, source, token and admission]
    A --> T[Receipt + encrypted SMS + index + outbox transaction]
    T --> D[Leased content-free delivery]
    T --> R[Authenticated archive and exact counts]
    R --> X[Bounded external assistant evidence]
    R --> E[Streaming personal export]
    X --> F[Fresh owner, consent and source check]
~~~

POST /api/v1/ingest/message uses Authorization: Bearer, not a session cookie. The compact wire fields are sender, date, body and o; event_id, schema_version and date_kind make retry and time provenance explicit. See the [wire model](../../apps/api/src/domains/sms/schemas.py) rather than duplicating its limits here.

Use an aware ISO 8601 string. Preserve text, normalize the instant to UTC and reject unsupported versions, invalid text, unknown fields or an excessively future timestamp. Shortcuts' capture time must be labelled captured; omission remains unknown.

A stable event UUID identifies one source event. The same event and payload is duplicate; different content under that identifier is conflict. Without an event UUID, the canonical payload digest is the identity. Changing the event identifier, timestamp or source can represent another event: this is not semantic cross-device deduplication.

Single-item responses distinguish stored, duplicate/ignored, conflict and invalid outcomes. A batch carries per-item verdicts; a successful HTTP response alone does not prove that every item was archived. A storage failure may leave commit acknowledgement unknown: retry the identical event, never invent a new identifier to get around it. Admission depends on Redis; unavailable admission fails before a write.

## Data, authority and privacy

Bodies and senders are encrypted at rest. Stable tenant HMAC material is wrapped separately from write credentials. The blind index supports bounded lexical search with exact verification after decryption; it is not an embedding index. Ambiguous broad searches ask for narrower criteria instead of claiming no match.

Receipts, credential hashes and index terms are operational, not plaintext export records. Erasure removes content/index/deliveries and keeps content-free replay tombstones. Receipt and archive limits are distinct; logical archive bytes are not a physical PostgreSQL disk cap.

Confirmed source mutations take the owner lock before credentials and source state. Provider contact IO runs outside the SQL fence, followed by fresh publication checks. Each concurrent source fetch uses its own session. Pending, leased, sent, cancelled and uncertain deliveries are not interchangeable; see the [uncertain-delivery runbook](../runbooks/alerts/PhoneIngestionDeliveryUncertain.md).

The SMS filter excludes recognized OTPs, passwords/access/recovery secrets, identifiable sign-in/reset links and blocked senders before storage. It cannot recognize every sensitive free-text message. No ingestion-triggered model or automatic memory extraction is added.

Assistant consent permits necessary excerpts to reach the configured model. Existing platform/BYOK quotas, pricing and LLM tracing policies still apply. SMS technical logs and metrics carry content-free codes and bounded labels, not the sender, body, raw credential or search text.

## Application integration

Settings place Mes SMS after Meetings. The archive has descending day and sender views, account-timezone grouping, bounded pagination, literal text and read-only content; block/delete/token actions use the approval flow. Contacts and relations are best-effort identity evidence, not verification of who sent a message.

Relationships expose exact SMS totals and a bounded list. Explicitly SMS-derived debriefs are invalidated when their source changes; SMS does not silently expand an existing debrief scope or become a portrait source.

The home card reads exact metadata without assistant access. Greeting/synthesis use only authorized bounded evidence; source changes after an awaited profile lookup prevent a paid SMS call, and changes during the model call suppress its text while retaining spent usage. SMS invalidation cancels in-flight home text, leaving regeneration to an explicit user action.

Both assistant modes use the same read-only list/search/get tools, strict schemas, proof, external-content envelope and native card. Long bodies continue at returned code-point offsets. Missing, stale, withdrawn or cross-owner proof fails closed at model boundaries and context re-serving. Ordinary non-SMS reference rendering retains its established output.

Immediate reception pushes follow the dedicated SMS toggle at any hour and contain no message text. Proactive useful-fact notifications use the heartbeat's own source switch, quiet windows and quotas. They require actionable offered IDs, not a receipt/unread claim; only successfully surfaced IDs receive mention metadata.

Private proactive content stays in authenticated LIA archive/SSE. Push preview is generic, external channel forwarding is suppressed, Radio excludes it before SQL limits, later decision windows exclude it, and continuity memory is skipped. No implicit Radio, phone, Live, peer or routine permission is introduced.

## Lifecycle and extension

Personal export includes readable SMS and user-owned metadata in bounded streams; encrypted internals and HMAC/search material are excluded. The structured JSON preserves source text; the readable Markdown quotes it literally so supplied HTML, image or formatting syntax cannot become active content. Hosted archives become unavailable after a source erasure that invalidates their snapshot. A downloaded copy, an earlier chat answer or a memory retained under the existing conversation preferences is not recalled by deleting the source SMS.

For another phone resource, add a strict resource contract and policy, reuse authority/admission/receipts/delivery where semantics agree, and declare its own models, purges/exports, readers, feature/consultation/action registries and UI. Do not bypass server approval or let a new catalogue entry grant unrelated surfaces access automatically.
