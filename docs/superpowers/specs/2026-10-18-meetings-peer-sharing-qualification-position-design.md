# Meetings search, peer capability transfer, JEV labels and place positions

Status: analysis only; implementation requires the owner's explicit go.
Date: 2026-10-18. Execution: strictly inline, without subagents.

## 1. Scope and decisions

The original request contained five changes. The owner withdrew the Word/PDF
header/footer change after source inspection established that both renderers
already supply a running title and pagination. No document-generation change is
part of this design.

The four remaining outcomes are:

1. Search all of the account's meeting minutes from the meetings list and show
   only matching meetings, with correct pagination and totals.
2. Send a skill, personal MCP configuration or installed plugin to an accepted
   peer. Automatically install an independent recipient-owned copy, disabled,
   without credentials, and show its sender and transfer instant.
3. Automatically qualify structured email/calendar observations through the
   native JEV runtime. Cards and the assistant receive the same accepted labels.
4. Automatically add one Position card for the Google Places included in a
   card-mode answer. Load its interactive Google map only after a click, showing
   the estimated cost before activation.

Owner decisions recorded during this analysis:

- Email priority is one mutually exclusive level: normal, urgent or critical.
- Email category also includes Phishing/Scam, displayed as the owner's exact
  French label 'Phishing/Arnaque', with a red blinking badge.
- A Position card appears automatically; paid map activation is explicit.
- A received skill has the execution capabilities of a recipient-authored skill
  after manual activation. This explicitly changes the default third-party
  treatment for peer transfers; it does not transfer administrator privileges,
  system-widget privileges, credentials, network approvals or connector grants.
- Implementation remains unapproved. Analysis documents do not grant permission
  to deploy, change runtime preferences, send anything to a peer, or publish.

No product decision remains blocking. The concrete interpretations below are
engineering recommendations, not additional statements attributed to the owner.

## 2. Evidence and limits

The inspected working tree contains extensive staged, unstaged and untracked
work, including adjacent document-generation, skills, display and configuration
changes. Implementation must re-inventory it and preserve those changes.
The source of repository instructions is [CLAUDE.md](../../../CLAUDE.md), with
[frontend additions](../../../apps/web/CLAUDE.md). AGENTS.md is generated.

| Verified source | What it establishes | What it does not establish |
| --- | --- | --- |
| [Meetings page](../../../apps/web/src/app/[lng]/dashboard/meetings/page.tsx), [list hook](../../../apps/web/src/hooks/useMeetings.ts), [repository](../../../apps/api/src/domains/meetings/repository.py) | List is paged; backend returns an exact total; selection is scoped to a page; no query parameter exists | A browser-only filter would search all minutes |
| [Meeting reports](../../../apps/api/src/core/meeting_reports.py), [list projection](../../../apps/api/src/domains/meetings/service.py) | Current minutes contain typed title, participants and sections; list projection reads report_current | Summary payload contains the minutes body |
| [Meeting indexing](../../../apps/api/src/domains/meetings/indexing.py) | RAG is an asynchronous projection which may fail while minutes remain ready | RAG gives complete, immediately current list filtering |
| [FAQ](../../../apps/web/src/components/faq/FAQContent.tsx), [normalizer](../../../apps/web/src/lib/utils.ts), [SearchInput](../../../apps/web/src/components/ui/search-input.tsx) | Existing search UX, accent/case/typography folding and debounced primitive | Frontend normalization can be replaced by identity casefolding without changing semantics |
| [Word](../../../apps/api/src/domains/document_generation/renderers/docx.py), [PDF finishing](../../../apps/api/src/domains/document_generation/renderers/pdf_layout.py) | Running title and pagination already exist | Current production revision or a historical downloaded file has been inspected |
| [Skills models](../../../apps/api/src/domains/skills/models.py), [preferences](../../../apps/api/src/domains/skills/preference_service.py), [trust](../../../apps/api/src/domains/skills/trust.py) | Ownership, provenance, per-user state and third-party execution are distinct concerns; imports create active personal states | Reusing import unchanged produces a disabled copy or authored execution parity |
| [Skill archive](../../../apps/api/src/domains/skills/archive.py) | Existing bounded resource archive protects against traversal, links and changing files | Every file in a skill folder is free of credentials or private output |
| [Plugin importer](../../../apps/api/src/domains/plugins/import_service.py), [hooks](../../../apps/api/src/domains/plugins/import_hooks.py), [group](../../../apps/api/src/domains/plugins/group_scope.py) | Plugins own ordinary skill/MCP rows; installation commits per component and reports partial outcomes; no global plugin enable field | A wrapper can make the whole existing import transaction atomic |
| [MCP service](../../../apps/api/src/domains/user_mcp/service.py), [schemas](../../../apps/api/src/domains/user_mcp/schemas.py) | Create enables a server; API-key/bearer creation requires credentials; ownership, quota and URL checks exist | A credentials-required create DTO can represent an unauthenticated received configuration |
| [Peer image transfer](../../../apps/api/src/domains/peers/image_share.py), [pair locks](../../../apps/api/src/domains/peers/pair_fence.py), [recipients hook](../../../apps/web/src/hooks/usePeerRecipients.ts) | Accepted-peer checks, independent copies, rate limits, sender metadata and lazy recipient selection are established patterns | Image transfer supplies capability installation or its durability contract |
| [JEV registry](../../../apps/api/src/domains/llm_config/jev_registry.py), [runtime](../../../apps/api/src/infrastructure/llm/jev_runtime.py), [transport](../../../apps/api/src/infrastructure/llm/typesafe_client.py) | Registered independent usages, database snapshots, quota enforcement, bounded native calls and actual spend accounting | Existing filter_email/filter_event label pro/personal/spam or urgency |
| [Collection qualification](../../../apps/api/src/domains/agents/display/jev_qualification.py), [preview](../../../apps/api/src/domains/agents/display/collection_preview.py) | Existing judgments are query relevance; preview is optional, ephemeral and absent on several surfaces | It is a synchronous classification service covering every email/event display |
| [Card payload](../../../apps/api/src/domains/agents/data_registry/card_payload.py), [LLM serializer](../../../apps/api/src/domains/agents/display/llm_serializer.py), [ReAct projection](../../../apps/api/src/domains/agents/tools/react_tool_wrapper.py) | Display-only metadata is withheld from models; generic serialization drops some nested dictionaries | Putting an annotation in meta or an arbitrary nested dictionary informs the assistant |
| [Briefing fetchers](../../../apps/api/src/domains/briefing/fetchers.py), [schemas](../../../apps/api/src/domains/briefing/schemas.py) | Dashboard mail/agenda bypass chat tools and have separate compact projections | A chat-only hook covers the dashboard |
| [Place formatting](../../../apps/api/src/domains/agents/tools/places_formatting.py), [Places client](../../../apps/api/src/domains/connectors/clients/google_places_client.py) | Formatted places use location.lat/lon; provider data uses latitude/longitude; lite search already requests location | Every legacy or malformed place has usable coordinates |
| [Route map](../../../apps/web/src/lib/google-route-map.ts), [React host](../../../apps/web/src/components/chat/markdown-route-map.tsx), [admissions](../../../apps/api/src/domains/connectors/map_load_router.py), [metering](../../../apps/api/src/domains/connectors/map_load_metering.py) | Native interactive maps, SDK singleton, explicit activation, quota admission and idempotent load reports already exist | Route polyline data or the GPS Location item is the requested multi-place map |
| [Response injection](../../../apps/api/src/domains/agents/nodes/response_node.py), [sanitization](../../../apps/web/src/lib/markdown-sanitize-schema.ts) | Data cards are injected after relevant-id selection; scripts/iframes are excluded from arbitrary answer HTML | Model-authored script/iframe content is an acceptable integration |
| [Account purge](../../../apps/api/src/domains/users/account_deletion_service.py), [export](../../../apps/api/src/domains/account_export/builder.py) | Explicit account deletion and export inventories exist; account erasure can scrub a user without firing FK deletion | New transfer/cache data is automatically purged or exported |

The supplied production URL could not be read through the web reader; no
authenticated production/browser comparison is claimed. External documentation
was checked against official Google and TypeSafe sources only for the decisions
used below. No paid provider call or peer transfer was made.

A targeted existing Word/PDF pytest run was started and subsequently interrupted
without a completion summary. It is not a passing test result. That feature was
withdrawn, so this analysis does not pursue its runtime qualification.

Documentation verification completed: task lint:docs:preview exited 0, with no
living broken links, stale living paths, living orphans or quoted-fact drift;
living maps were current. It also reported 17 historical broken links, 304
historical stale paths and 22 roadmap stale paths outside these two new files.
An independent existence check found no unresolved relative file/document links
across the two deliverables. This is documentation evidence, not behavioral
test evidence.

## 3. Meeting search

### Functional contract

- Search is lexical, case/accent insensitive, with the FAQ's typographic folding.
  A trimmed contiguous query matches within an individual searchable text field.
  This is not semantic retrieval, fuzzy search or an undocumented AND query.
- Search title, participant names/roles, location, section headings and the actual
  content of each section: paragraphs, bullets, topics, actions, and rewritten
  transcript sections when these are part of the minutes.
- The encrypted original transcript, original superseded minutes, template keys,
  JSON field names, engine diagnostics and internal ids are not searched.
- Empty query retains the current unfiltered list, including live/failed rows.
  Nonempty query matches the current report, including the last valid report
  retained during regeneration. A row without current minutes cannot match.
- Suggested API: add optional q to GET /meetings, bounded to 200 input characters.
  Query strings are bound parameters; percent, underscore and escape characters
  remain literal characters, not SQL wildcard instructions.
- Count and page use exactly the same owner and match predicates. Order by
  started_at DESC, id DESC for stable equal-time ordering. Never count a page.
- Search changes reset offset and selection. Preserve q, page and from on
  list/detail/back navigation and browser history. Clear returns to page one.
  Old deep links without q retain their meaning.
- No-match emptiness keeps the input, count and clear action. Network failure is
  distinct from zero results; a stale response cannot publish another query's
  rows or count. A retained list while refreshing must state that it is updating.

### Implementation choice and consequences

Counter-review correction: a persisted projection and backfill were specified
before demonstrating their necessity. The simpler baseline is a query-time SQL
projection of the permitted text fields from report_current and location_label,
with the existing owner index. This needs no new persisted search column,
writer synchronization or backfill. Editing/reset/regeneration are immediately
reflected because the predicate reads the canonical fields themselves.

Use static, schema-owned JSON paths, a section-kind completeness guard and typed
scalar extraction; never search the raw JSON representation or all its strings.
Match with EXISTS per extracted field, so a phrase cannot cross two unrelated
fields. Missing/mistyped values must not abort the list or turn diagnostic and
structural fields into searchable content. The caller never supplies a JSON path.

Use a SQL normalization expression with NFD, lowercase, the same combining-mark
range and typographic substitutions as the frontend, pinned by a shared corpus
on real PostgreSQL. Reuse core/sql_search.escape_like and LIKE_ESCAPE. Existing
unaccent searches demonstrate the repository's native SQL-search pattern, but
unaccent and fold_name are not presumed equivalent to normalizeSearchText; do
not silently change its ligature/Unicode behavior to simplify the query.

The database facilities are available in the documented PostgreSQL generation:
[JSON path/scalar extraction](https://www.postgresql.org/docs/16/functions-json.html)
and [Unicode/string operations](https://www.postgresql.org/docs/16/functions-string.html).
This establishes API feasibility, not measured query performance. UTF8 encoding
and actual normalization/collation behavior are integration-test prerequisites.

Build the filtered set once in a single statement/snapshot, deriving the exact
total and limited rows from it. Preserve the total even when offset is beyond
the final row: a window count attached only to returned rows cannot do that.
Exercise concurrent edits/deletions, not merely identical SQL WHERE clauses in
two READ COMMITTED statements.

Measure representative long reports and large account histories with EXPLAIN,
latency and memory. A persisted/indexed projection is a contingent optimization
only if the native query fails that measured gate; it would then require an
amended plan covering all writers, backfill, rollout and migration replay.
It is not included as an unconditional feature cost. No deployment is authorized.

## 4. Peer capability transfer

### Ownership and lifecycle

Share through a row action and a lazy peer picker, using only accepted,
unblocked connections. Recipient identity is resolved by the server from the
connection, not trusted from the client. A direct intentional UI send is the
sender's instruction. Any later assistant-facing share tool must enter the
existing server-enforced confirmation flow; this design does not introduce an
unconfirmed autonomous cross-account write.

Enforce the existing peer and resource capability switches on the server for
the operation's two accounts. Installation quotas, per-sender/per-pair daily
transfer limits, recipient incoming-install/byte limits and bounded snapshot
retention also apply. No retry may bypass a recipient cap or silently queue an
installation for a later time when the disabled feature becomes available.

The sender can transfer only resources they are authorized to export/read in
the exact scope. An accessible exportable system skill may become a personal
copy; it never becomes a system skill. MCP transfer covers personal servers,
not administrator-owned shared infrastructure. A plugin transfer uses the
current installed package and its live owned components, not a fresh download
from a mutable upstream URL.

Transfer creates independent local ids and storage paths. Changes, deletion,
deactivation or disconnection on the sender's side do not update or revoke an
already completed recipient copy. Re-sharing names an immediate sender; it
does not expose the first sender's identity through a transitive social graph.

Proposed receipt contract: transfer id, actor, recipient, resource kind,
sanitized snapshot digest, accepted transfer instant, installation status,
component outcomes and recipient resource identities. A stable idempotency key
returns the original result after a lost response. A different key never
silently overwrites an existing resource: return an explicit conflict. No
automatic rename of a plugin, whose internal names/references are meaningful.

Preserve the existing system-skill collision guard. Request-state resolution
gives a personal skill precedence even when disabled; bypassing that guard could
therefore hide an active system skill merely by receiving an inactive copy.
A system-name collision reports already-available/conflict and creates nothing.
It must not disable, rename or shadow the existing skill.

Proposed lifecycle: preparing -> installing -> installed | partial | failed,
with a cancelled terminal outcome for a transfer invalidated before publication.
Every value must have a producer, reader, retry rule and localized presentation.
Persist a durable claim before work, settle only from actual outcomes, and
reconcile interruption/unknown commit acknowledgements before any replay.

Installation is automatic, activation is not. Every created UserSkillState is
inactive and every created MCP server is disabled at its FIRST commit. Importing
enabled and disabling afterwards has a real execution race and is forbidden.
No automatic discovery, OAuth redirect, connector call, script execution or
model-generated description happens on receipt. Disabled resources still count
toward ordinary installation/storage quotas.

Plugins have no global on/off column today. A received plugin is disabled by
disabling all executable installed components; its row shows that aggregate.
Keep the current per-component enable controls and uninstall semantics. Do not
invent a second plugin state which can disagree with those controls.

### Transfer data and credentials

Use closed transfer DTOs, never ORM serialization or filesystem copy-all:

| Kind | Included | Excluded |
| --- | --- | --- |
| Skill | Validated SKILL.md, intended scripts and static declared resources | Runtime out/, temporary/generated user data, local configuration, credential files, links/junctions, source paths and account identifiers |
| MCP | Validated endpoint, name/description, transport, timeout, iterative preference and authentication requirement | Credentials/encrypted blobs, API keys, bearer/refresh/access tokens, OAuth client secrets, grants, sessions, discovered-tool caches, embeddings and learned usage |
| Plugin | Validated manifest and intended static package; sanitized MCP definitions and recipient-owned component identities | Sender runtime state, credentials, caches, approval records and user data; no stale unsanitized original mcp.json alongside a sanitized DB row |

Preserve authentication requirements. A received API-key/bearer/OAuth server
remains disabled and auth_required until the recipient configures it. Existing
public create validators must remain strict; add an internal credentials-free
installation DTO/method which shares the existing quota, ownership and SSRF
checks. Validate a public endpoint at receipt and again at connection time;
DNS validation is not permission to bypass network restrictions.
Reset the sender's per-server HITL override to None, inheriting the recipient
instance's MCP_HITL_REQUIRED policy. It is an authority preference, not a portable
credential-free server property. Do not copy learned approvals or allowlists.

Credential readiness and activation are separate transitions. Current
update_server saves credentials without making an auth_required row active;
toggle_server changes is_enabled without changing status. Therefore the received
flow must include the existing explicit connection-test/OAuth completion path,
which validates readiness and refreshes tools/status, while keeping is_enabled
false. Only the recipient's subsequent enable action exposes the server to the
assistant. A failed test preserves disabled/non-ready state. Connection testing
may invoke existing description/embedding work and must use its normal recipient
accounting/limits; it is never hidden inside automatic receipt.

A secret may also be embedded in URL paths/query parameters, static headers,
scripts or reference text. Structured exclusion can be guaranteed; detecting
every arbitrary embedded secret cannot. Build the static inventory, omit
known runtime/config files, allowlist non-secret headers, scan the package and
refuse a suspicious/unresolved package with a precise code. Do not claim that
Fernet exclusion alone guarantees a secret-free archive. Show the sender the
actual sanitized inventory/omissions before send; do not silently break a
script by redacting arbitrary source literals.

### Authored-equivalent execution, explicitly authorized

Keep acquisition provenance and execution policy separate. Proposed new
SkillProvenance.PEER records a standalone copy's arrival; plugin children retain
their plugin ownership/provenance and carry the transfer origin. Add a closed,
server-written peer execution policy which resolves to the authored policy at
the request-state chokepoint. This covers standalone skills and skills received
inside a plugin. It must never be accepted from an upload's frontmatter.

Update the one trust resolver, request-state construction, gallery/native
projections and round-trip contracts. An active received skill may use the same
catalogue, prompt injection, plan templates, always-loaded behavior, connector
tools and ordinary rich output as a recipient-authored skill. It runs with the
RECIPIENT's granted capabilities and existing HITL, sandbox and egress rules.
It receives no administrator or privileged system-widget identity.

Edits made through the recipient's authored editing paths retain this policy
and the historical badge. A later upstream/library/plugin replacement must
resolve trust from its own new import channel, never inherit a peer policy for
unseen third-party bytes. A resend is a new disabled copy/conflict, not an
automatic trusted update. Plugin-managed components retain normal group rules;
the policy exception does not turn a plugin child into a standalone editable
skill behind its parent's back.

This is an explicit amendment to CLAUDE.md and ADR-327, not a claim that current
code already permits it. Regenerate AGENTS.md from CLAUDE.md. Preserve the
unchanged URL/library/ordinary-plugin isolation policy in regression tests.

### Durability, notification and privacy

Reuse the import validation/staging, lifecycle locks, cancellation/commit hooks
and cross-worker cache invalidation. Extend importers with a caller-supplied
initial activation policy and origin hook; default ordinary imports to their
current behavior. Do not globally change import defaults.

The plugin importer already commits components independently. Preserve that
contract and make the new transfer resumable per component, with deterministic
recipient identities and terminal partial reports. An installed plugin with
skipped components must not be reported as complete. All surviving partial
components remain disabled. Preflight package shape, quota and conflicts before
publication; retry only the receipt's missing work after rechecking ownership.

Each committed component outcome records its recipient id, installed content/
configuration fingerprint and receipt identity in the same commit as that
component. Callbacks after commit alone cannot supply this durability: a crash
can occur between the SQL commit and the callback. Reconcile an unknown
acknowledgement from these durable facts. A retry never upserts an already
completed component. If the recipient edited, activated, deleted or replaced
it, preserve that action and do not recreate it or reset its activation state.
A missing component is created only while its receipt still owns its reserved
identity; another local resource using that name is a conflict, not an update.

Lock peer identities in canonical order for publication checks, with consistent
ordering relative to existing resource-owner locks. No pair/database lock lives
across package IO, DNS, models or notification transport. If a block/removal
wins before the publication authority check, refuse further publication.

Notification follows durable installation outcome and is deterministic, using
the existing notification pipeline. Its failure does not roll back a valid
installation; retry it idempotently. Never notify a blocked sender about the
block. No LLM is needed to relay this package or write a notification.
File the intentional send and its outcome through domains/shared/action_sink,
using a bounded declared capability and receipt-derived idempotency. Register
it in the existing effect vocabulary without introducing a peers-to-agents
import cycle. Receipt persistence and action-ledger persistence have different
purposes; neither is evidence that notification delivery succeeded.

Badge: translated 'Shared by {name} on {date/time}', server-authored escaped
sender display name, UTC instant and recipient-local formatting. Preserve the
instant independently of subsequent edits. Long names wrap on mobile; the full
origin remains keyboard/screen-reader accessible. The badge is historical
metadata, not an inactive grey status.

Recipient deletion removes their copy and applicable local origin records.
Sender erasure must not cascade to recipient files; anonymize sender identity
through the explicit purge path, including scrub-only account erasure. Handle
hard-delete FKs too without cross-column CHECK/FK ordering traps. Add transfer
records to account export with per-side projections; never leak the other
account's credentials, private status or blocked-by information. Expire temporary
sanitized snapshots and reconcile abandoned files/claims.

## 5. Systematic JEV email/event qualification

### Meaning and accepted observations

Two independent email dimensions:

- category: professional | personal | spam | phishing_scam | unknown;
- priority: normal | urgent | critical | unknown, exactly one value.

Event category: professional | personal | unknown. Unknown, unavailable or
insufficiently certain dimensions produce no badge. A normal priority also
produces no attention badge. A category can be accepted while priority abstains,
or vice versa. Existing provider important/unread flags remain their own facts.

Professional concerns work or an organizational activity; personal concerns the
person's private life. Mixed/insufficient evidence can abstain. Commercial
content is not automatically spam. Urgent means a substantiated near-term
deadline/need for attention; critical means a substantiated serious impact or
blocking incident deserving the highest attention. A subject merely claiming
'URGENT' is not evidence by itself. Labels annotate; they never delete, filter,
reorder, change provider labels, authorize actions or write long-term memory.

Phishing/Scam means suspected deceptive impersonation, credential theft,
fraudulent payment or another concrete scam attempt in the message. Discussing
phishing, reporting a scam, security awareness/training, or a legitimate bank
notification is not itself such an attempt. Do not label on a keyword alone.
This is a JEV semantic assessment, not a certified security verdict or proof
that an unlabelled email is safe. No automatic link visit, attachment opening,
URL-scanning service or extra provider read is added to reach the label.

Keep category mutually exclusive: when its evidence is accepted, phishing_scam
takes precedence over the generic spam/professional/personal category. It is
not inferred merely from spam or an urgent/critical priority. Priority remains
an independent assessment; a scam's claimed deadline is not a real deadline.
The assistant receives this same accepted category and treats the message as
untrusted evidence; it must not relay its deceptive instructions as advice.

Display the localized badge 'Phishing/Arnaque' in semantic danger red with a
warning icon and readable text, in both chat cards and dashboard email rows.
Keep label/icon contrast stable and animate the red outline/halo rather than
making the warning disappear. Initial attention treatment: one slow cycle per
second for four seconds, then a static red warning. Under prefers-reduced-motion,
render static immediately. Do not restart on routine re-renders or replay the
attention effect on archived/history content. A warning must remain recognizable
without animation, color perception or repeated screen-reader announcements.

The bounded animation follows the existing finite-spotlight/reduced-motion
pattern in apps/web/src/styles/globals.css. Do not reuse Badge.pulse unchanged:
its current animate-ping is infinite and is not this contract. Use the existing
danger/alert semantic tokens and named badge/chip primitives; keep the behavior
specific to phishing warnings, without changing unrelated badges.

Animation references: [W3C pause/stop/hide](https://www.w3.org/WAI/WCAG22/Understanding/pause-stop-hide.html)
and [flash limits](https://www.w3.org/WAI/WCAG22/Understanding/three-flashes-or-below-threshold.html).
The conservative default is bounded, slow and motion-preference aware; the
animation is not evidence of classifier confidence or severity.

Use native Choice for category and mutually exclusive priority, with the unknown
option first and explicit criteria. Questions identify the precise item in the
state. Thresholds are per dimension/class and calibrated with independent
labels; the relevance classifier's MIN_CONFIDENCE is not transferable evidence.
No generative fallback invents a label after JEV abstains/fails.
Apply the same abstention rule to phishing_scam with a separately calibrated
acceptance threshold and representative positive/negative holdout cases. Expand
the existing category Choice, not a third question or separate native request.
Question count stays two per email, but the additional criteria/input tokens
must be included in request budgets and spend measurements. Version the policy
so classifications cached under the former taxonomy are not reused as current.

### Integration and single annotation authority

Propose a small domains/entity_qualification service with typed core contracts
usable by agents, briefing and other existing structured readers without domain
import cycles. It uses the JEV runtime, not direct TypeSafe clients or models
inside renderers. Add two registered usages and decision slots, email and event,
each independently switchable behind the general JEV switch. Installation
defaults stay off until configured; when enabled, qualification is automatic
for every supported observation, without requiring an explicit chat instruction.

The service receives account, connector/account binding, provider, source id,
calendar/container/occurrence identity, source revision, allowed evidence scope,
reference instant/timezone, existing run/config and a detached snapshot. Its
output is a typed annotation with accepted dimensions, JEV model/policy version,
evaluation time, evidence fingerprint/scope and expiry. Raw bodies/probabilities
do not belong in the ordinary UI annotation. Provider-supplied fields cannot
forge an internal annotation; internal fields are constructed after normalization.

Chat seam: after provider normalization and the selected email detail shaping,
before registry/context/SSE publication. Never upgrade metadata to full detail or
read display-only meta to feed JEV. Summary can use its permitted digest; full
can use its permitted body. Oversized/incomplete evidence is stated as such and
abstains when the requested property needs unseen evidence. Do not silently cut
a full message and claim to have classified its whole contents.

Use the same annotation in structured_data, registry payload, context store,
ReAct projection and response projection. A typed object only inside meta is
invisible to models; the generic response serializer also drops arbitrary
nested objects. Add an explicit, bounded annotation-to-model projection and
test the final model inputs, not merely the presence of a field on a Python
object. Keep raw probabilities, diagnostics and cached bodies out of it.

Dashboard seam: briefing fetchers qualify allowed normalized mail/event
observations before their compact DTO projection/cache. Extend backend/frontend
DTOs and MailsCard/AgendaCard; synthesis receives the same accepted values.
Inventory other structured email/event surfaces through direct_client_callers,
consultation_surfaces and actual registry producers, including relationship
views and background/voice consumers. Reuse the service at each serving boundary.
Do not call a chat-only patch 'systematic'. Arbitrary quoted prose in a document
is not a new structured entity to classify.

This does not add qualification to every low-level connector read. Background
mailbox indexing, source synchronization, availability-only scans and internal
reads that produce neither a displayed entity nor evidence for the current
answer must not incur new JEV calls merely because they use the same client.
The serving-surface inventory distinguishes those reads explicitly. Budget
exhaustion/incomplete coverage is recorded as unqualified, never silently
converted to normal or personal.

Stored chat answers remain historical snapshots. Opening history/bookmarks or
re-rendering a card makes no provider call. A fresh authorized source read may
requalify a changed/expired item. No eager sweep of a mailbox/calendar is needed.

### Budgets, caching and degradation

The current native transport permits at most 24 questions and 32,000 request
bytes; reference its constants, never duplicate them in application logic.
Email uses two Choice questions per item, event one. Thus the question ceiling
alone allows 12 emails or 24 events per batch, often fewer under the byte/token
budget. Bin whole, bounded observations with their ids; do not misalign answers
after filtering, batching, partial provider failure or reordered input.

Use a configurable per-observation/operation token, byte, concurrency and total
time budget. Estimate tokens on the final request; the byte ceiling is not a
token budget. Keep a bounded queue; admit before native spend; stop optional
work when the parent is cancelled and await/close all tasks. No AsyncSession
is shared across workers or held over the model call.

Cache by user + actual connector/account binding + provider + container/item/
occurrence + evidence digest + detail scope + policy/model version. Urgency
also expires according to its reference-time validity, rather than living as
long as an immutable message id. No cross-account or cross-grant cache reuse.
Cache accepted unknowns for a short period to avoid paying for every refresh;
separate transient unavailable/backpressure outcomes from semantic unknowns.
Coalesce concurrent misses, including workers, with existing bounded owner-token
flight patterns; Redis failure is a visible degraded path, never leaked data.

Declare the Redis family USER_CACHE, with TTL, reset/forget/account-purge handling.
Do not add a per-turn state key or a psychological/identity memory. Context
round-trips preserve the accepted annotation and its source binding; a changed
source invalidates a previous badge before publication.

Both account and instance ceilings apply: JEV provider keys are instance-owned.
Every paid batch, including an invalid paid answer, is counted once by the
existing runtime. A shared batch is not charged once per question. Reuse the
turn accountant or establish an attributed out-of-turn act for briefing/other
readers and declare its spend/decision road. Cache hits have no native charge.
Usage-limit refusal, 429, timeout, missing key/model/price and disabled routing
produce no new label and no paid fallback; preserve already-authorized source
results. Do not swallow cancellation or weaken the enclosing request's quota gate.

Incremental model cost is the sum of actual batch input/output counters at the
database tariff plus the accepted annotations' extra downstream context tokens.
The result is additive work; no net saving is claimed. Measure cache-miss rate,
coverage, class precision/false positives, abstention, tokens/cost per actual
display and end-to-end P50/P95 latency, not native-call latency alone.

## 6. Position card for returned Google Places

Project from the final relevant current-turn place registry after answer
selection, not all historical registry items. For reference turns, use only the
explicit resolved selection. Include real Google Places, including selected
correlated places, once per place identity. Exclude unrelated search text,
invented locations, GPS LOCATION and places the response discarded.

Emit one native aggregate card named Position, after the place cards, in the
existing card display modes. It is a display projection, not a new domain,
tool, LOCATION item or always-on SKILL_APP. The model does not choose coordinates
or author executable HTML. Do not add the map's coordinates/data to its prompt.

Proposed versioned wire contract: places with stable local id/card reference,
label, validated finite lat/lng, safe Google Maps link, and explicit counts of
unlocatable/omitted points. Support current lat/lon and documented legacy
latitude/longitude shapes. Zero coordinates are valid; NaN, infinity and
out-of-range values are not. Use an exhaustive projection rather than passing a
provider dictionary to the browser.

The card appears whenever the selected answer has a place. An unlocatable place
remains in the accessible list with its link and a stated missing position;
never invent its marker or incur a hidden geocode/detail lookup. If no selected
place has coordinates, keep that explanatory card/list without map activation.
Every valid distinct place has a marker. Shared coordinates retain distinct
identities, with an accessible overlap chooser/list. Do not silently take the
first N points: larger valid sets must be chunked/clustered or have explicitly
stated overflow while preserving the complete list and user control.

One point uses a capped useful zoom; several fit their bounds. Handle remote
clusters, coincident points and the antimeridian. Link/marker selection should
relate to the existing place card without inventing a new tool reference.

Reuse SDK loading, admission, load reports and failure ownership from route maps.
Extract only the truly shared SDK/lifecycle/metering pieces; route polylines and
place markers remain separate typed controllers. Add lazy React enhancement of
the server-owned inert sentinel, with a usable initial list/fallback. The
sanitizer remains closed to arbitrary scripts/iframes. Strip model-authored map
sentinels and prevent duplicate injection, including archived/replayed output.

Use supported AdvancedMarkerElement, with its marker library and a configured
map ID. Keep the existing route map's JSON-style/theme behavior intact: adding
a map ID globally would change that behavior. Place-map theme setup follows
the supported map-ID/color-scheme contract; do not silently reconstruct maps
and incur another load on every theme change.

The public config publishes availability, map id and estimated tariff only;
credentials are fetched through authenticated admission. A production browser
key must be restricted to the required API and allowed origins. Existing
browser_maps_key falls back to the server key; reuse the admission protocol but
do not introduce a new path exposing an unrestricted server key. Validate the
place-map capability server-side, independently of the route feature's UI flag.

The cost shown comes from the current Dynamic Maps tariff. No spend for merely
rendering/reopening the initial card. Each actual Map construction is reported
once with the same signed account-bound token across retries; no admission-time
invented charge. Existing metering observes construction, not a provider invoice.
SDK/key/adblock/CSP/offline failures retain links and show a retry. A quota
denial leaves the card useful. Late async completions cannot attach to an
unmounted/account-switched card. Dispose listeners, observers, markers and DOM.

UX: full-width mobile card, cooperative gestures, named region/controls,
keyboard marker/list equivalence, predictable focus, no color-only meaning,
Google attribution preserved, reflow/zoom and light/dark/OLED support. No request
for the user's GPS is needed. No geocoding/Routes/Places SDK lookup is introduced.

Official references checked on 2026-10-18:

- [Maps Embed modes](https://developers.google.com/maps/documentation/embed/embedding-map):
  place/search/directions modes do not provide the exact arbitrary marker set
  this contract requires; using a search embed would change the returned set.
- [Advanced markers](https://developers.google.com/maps/documentation/javascript/advanced-markers/overview):
  supported markers include keyboard interaction and require a map ID.
- [Map color scheme](https://developers.google.com/maps/documentation/javascript/mapcolorscheme)
  and [map IDs](https://developers.google.com/maps/documentation/javascript/map-ids/mapid-over).
- [JavaScript API billing](https://developers.google.com/maps/documentation/javascript/usage-and-billing):
  map loading and other API calls have their own billing/quota contracts.
- [TypeSafe Choice](https://docs.typesafe.ai/primitives/choice) and
  [confidence](https://docs.typesafe.ai/confidence): bounded choices, grouped
  questions and distribution concentration do not establish domain accuracy.

## 7. Impact and risk matrix

| Area | Direct/indirect impact | Risk | Concrete mitigation |
| --- | --- | --- | --- |
| Meeting DB/API/list | Native read-time projection, q, exact count, selection/navigation | High: wrong scope, field matching or page/count snapshot | Explicit typed fields; canonical current report; one query snapshot; real PostgreSQL tests |
| Search privacy/performance | Query URLs, large histories, JSON extraction | Medium: URL/log retention, long scans | No extra persisted private text, no search-content logging, bound q, measured queries; document URL query persistence |
| Peer authority | Cross-account writes and source authorization | High: wrong recipient, block races, scope capture | Resolve accepted pair server-side, canonical locks/final fences, exact owner ids and no foreign overwrite |
| Installation | DB/files/cache and component commits | High: transient active copy or false success | Initial disabled state before first commit, resumable receipts, partial reports, cancellation/unknown-commit tests |
| Secrets/packages | Credentials and arbitrary package files | High: secret/private-data transfer | Closed DTO/static inventory, sanitization of every copy, scanner/refusal and revalidation; explicit limit of embedded-secret detection |
| Skill trust | Peer execution parity and later updates | High: accidental system privilege or inherited third-party trust grant | Orthogonal server policy, recipient permissions, preserve system distinction, new-import trust resolution, explicit ADR/CLAUDE update |
| User lifecycle | Export, scrub/hard-delete, copy ownership | High: delete peer copy or retain identity | Explicit per-side purge/export, anonymize sender without deleting recipient resource, real FK tests |
| JEV quality | Ambiguous/multilingual/adversarial inputs | High: spam/critical false positives | Unknown, class-calibrated thresholds/holdout, displayed suggestions only, no filtering/actions/memory writes |
| JEV delivery | Tool, ReAct, pipeline, briefing, compact DTOs | High: badge/model disagreement | One typed annotation and explicit model projection before publication; inspect actual prompts and round-trips |
| JEV spend | Batching, caches, workers and background paths | High: repeated platform charges | Both ceilings, runtime accounting, whole-scope keys, bounded shared misses, no generative retries, total time budget |
| Map selection | Current vs history, filtered/correlated entities | Medium: phantom or missing markers | Aggregate final selected places once; schema validation, complete lists and explicit coordinate gaps |
| Map runtime/cost | Shared SDK, key, map ID, theme, quotas | High: route regression, exposed server key, repeated load | Shared loader without route behavior changes, restricted browser credential, authenticated activation, idempotent reports |
| Frontend | Locale, account lifetime, stale requests, accessibility/mobile | High on cross-account/stale paths | Existing typed hooks/account guards, abort transports, retained focus, six locales, hermetic browser tests |
| Architecture/docs | New module/type/switch/import edges | Medium: cycles, dead registry member, documentation drift | Existing ports/composition, completeness guards, no local-import cycle hiding, shrink-only ratchets and living maps |

## 8. Test director and acceptance gates

| Lot | Unit tests | Integration / flow | Browser / real-render proof |
| --- | --- | --- | --- |
| Meetings | Exhaustive field projection; normalization parity; empty query and literal wildcards; query/history/selection lifetimes | PostgreSQL current-only matches, cross-owner isolation, total/page equivalence even beyond final offset, all mutation paths and concurrent edits | Search a result outside page one; no-match/clear; rapid queries reversed; detail/back; delete last matching row; 320px/zoom/keyboard |
| Transfer | Closed DTO/redaction, package inventory, trust matrix, initial-state policy, state vocabulary and idempotency | PostgreSQL + temporary files: all three kinds; partial plugin; quota/conflict; concurrent duplicate send; block race; crash/cancel at every import boundary; lost commit; sender/recipient scrub/hard-delete; export | Peer picker lazy read/error/none; truthful installed/partial/failed; disabled copy visible; credentials configured then explicit activation; local edit/uninstall; long origin badge and account switch |
| JEV | Category/priority gates, independent abstention, token/byte batches, stable ids, cache keys and expiry, no forging, serializer and checkpoint round-trip | Mocked native HTTP with real runtime accounting; pipeline/ReAct actual model inputs; dashboard DTO+synthesis; same ids across two grants/accounts; worker duplicate misses; source revision change | Email/event badges match assistant context; normal/unknown absent; all providers; no API call on history; 429/timeout/disabled still show results; mobile/keyboard/readers |
| Position | Coordinate variants/ranges/zero, dedup, filtered/correlated/ref turns, wire validation and sentinel stripping | Actual response injection -> archived HTML -> sanitize -> React host; authenticated admissions and two-worker duplicate reports; no geocode/provider call | Mock official SDK at boundary; one/many/coincident/remote points, keyboard/list equivalence; no map call before click; quota/key/offline/cancel/retry; theme/route coexistence and no extra construction |

Simulation inventory: mixed-language mail, sparse metadata, huge body, HTML
injection/instructions inside mail, marketing that is not spam, credential theft,
fraudulent invoices/payments, impersonation, legitimate security/bank messages,
training/reporting about scams, forged urgency, low-confidence phishing, category
precedence, phishing/priority independence, old-taxonomy cache invalidation,
multiple simultaneous warning badges, reduced motion and finite-animation replay,
personal/work overlap, missing sender, calendar cancellation/all-day/recurrence,
same event id in distinct calendars, changed timezone/deadline, NaN/Infinity,
malformed/partial JEV JSON, unexpected model/answer ids, 429/Retry-After,
configuration switch during work, paid-invalid answer and cancelled paid body;
Redis unavailable/expired owner, SQL rollback/unknown commit, filesystem full,
archive bomb/link/junction/traversal/change-during-read, inline URL/header
secrets, plugin component conflicts, expired/deleted peer, lost notification,
stale account-scoped UI callbacks, archived map replay and two different maps
sharing one SDK load.

Calibrate JEV with a separate labeled multilingual corpus and a frozen holdout;
measure class precision, false-positive rate, abstention and coverage, then
end-to-end cost/latency with cache-cold/cache-warm and source-updated runs.
Thresholds cannot be declared empirically validated during source-only analysis.
No production mailbox or paid test is implicit in this plan.
Freeze acceptance criteria before the holdout is evaluated. A classifier which
abstains on everything is not a successful implementation: deterministic tests
must accept the unambiguous positive fixtures and reject/abstain on adversarial
and ambiguous ones. Report holdout sample counts per class, observed false
positives (especially phishing_scam/spam/critical), coverage and uncertainty; tune only on the
calibration split. Passing mocked contracts alone does not authorize enabling
the new usage in production.

During implementation, use failing behavioral tests -> minimal implementation ->
passing tests for each atomic lot. Run task lint, the relevant backend/frontend
gates and coverage; migration changes require task db:migrate:replay-check on a
disposable database. Before any separately authorized push: task ci:fast. Use
Docker dev for runtime browser proof; no host Next dev/build outside that workflow.
Keep service/browser tests and their prerequisites explicit. Do not lower
coverage, enlarge complexity/file/a11y/hooks debt or suppress warnings.

## 9. Formal self-review

| Requested criterion | Verdict |
| --- | --- |
| All product ambiguities that could block implementation resolved | Yes, with the owner's explicit decisions and the engineering interpretations stated above |
| Existing functionality inspected rather than assumed | Yes for the contracts cited; no production equivalence is claimed |
| Whole-path impacts, tokens/costs, registries, persistence and responsive UI addressed | Yes, with individual failure/acceptance gates above |
| Implementation and tests can start immediately | Yes, following the corrected companion plan after the owner's go; native-search performance and semantic calibration remain explicit acceptance gates |
| 100% guarantee of runtime quality or JEV accuracy | No: real PostgreSQL/filesystem/browser evidence, calibration and load measurements remain implementation acceptance work |

The source audit supports architectural feasibility. It is not a completed
implementation, performance benchmark, production certification or a promise of
zero residual risk. Re-read the concurrently changing files before editing.
