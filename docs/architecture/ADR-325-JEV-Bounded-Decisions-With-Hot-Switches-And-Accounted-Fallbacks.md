# ADR-325 — JEV makes bounded decisions, with hot switches and accounted fallbacks

**Status:** Accepted — 2026-09-29, following the owner's approval of the JEV integration lots.

**Scope:** Native decision provider, independently switchable integrations, diagnostic
visibility, accounting and evaluation. Acceptance of this architecture does not
activate an integration or certify a production deployment.

**Amendment — 2026-10-04:** The owner requested hiding the intermediate
“first results” panel from the discussion, while retaining every JEV usage and
its independently switchable configuration. The response node still schedules
collection qualification and builds authorized document projections. Their
existing diagnostics remain available in the administrative debug panel;
the canonical registry, synthesis context and final cards retain their authority.
Ephemeral preview frames are invisible in chat and do not count as a first useful
delivered result. Hiding the panel neither deactivates inference nor establishes
a cost or end-to-end latency gain.

The HITL exclusion usage also judges reference scope independently from the
per-item exclusions, over the same state in the same native batch. A singular
reference may match several names without identifying which item the person
meant; confident item answers alone do not resolve that ambiguity. The consumer
requires a clear scope and valid item answers, otherwise the whole list follows
the existing fallback. One question slot is reserved for scope, and its separate
confidence policy does not lower the per-item policy. Debug labels expose that
judgment. The result remains a proposal requiring the existing human confirmation.

**Amendment — 2026-10-11 (questions aligned with the vendor's documented practice):**
the transport carries the documented Noul primitive and structured instructions
and criteria (``typesafe_client.NoulQuestion``; Noul answers travel in
``DecisionAttempt.nouls``, the panel draws them as two outcomes). A question
changes only when a measurement on its usage's own calibration and holdout corpora
shows no more wrong shortcuts and at least the same coverage. Four questions
passed and changed: the initiative utility (a Noul, skip at p ≤ 0.11), the
consultation selectors (one structured question, the conservative ``other``
first, the request fields only, one threshold of 0.97), the radio verifier (one
Noul per line, decided at p ≤ 0.16 or ≥ 0.84) and the collection qualification
(structured, ``unknown`` first, 0.94). The memory reference presence, the HITL
refusal and the HITL exclusion kept their wording: their aligned candidates
covered less or erred more. Evidence and method:
[JEV_SEMANTIC_QUALIFICATION.md](../technical/JEV_SEMANTIC_QUALIFICATION.md).

**Amendment — 2026-10-11 (guarded parameter values):** a new usage,
``parameter_kind``, judges what a value bound for an address, place or email
parameter IS (one Choice per distinct value, the measured d5 question); the code
decides whether the parameter accepts that kind. It runs only after the
deterministic guard let the call through and only ever adds a refusal (ADR-120,
amendment 2026-10-11). Its decisions join the turn's tracker, so their cost lands
on the turn's own summary.

**Amendment — 2026-10-25 (what reaches the model, and what comes back used):** an audit
against the vendor's documentation and seven days of production found the usages
starved rather than wrong ([evidence](../superpowers/qualification/jev-audit-2026-10-25/README.md)).
Five decisions follow.

1. **The transport admits what the vendor documents.** A request is refused locally only
   when its estimated tokens exceed 64k for the whole request or 32k for the state plus
   any one question (the documented contexts of Jev 1.13 and 1.14); the estimate is the
   local tokenizer × 1.25 plus measured overheads, never exceeded by more than 87 % on 201
   billed requests. The former 32 000-byte / 24-question cap had no vendor counterpart and
   refused every real initiative state (109 kB). Usages that put several items in ONE state
   keep the batch shape they were measured with (`JEV_SHARED_STATE_BATCH_BYTES`).
2. **One keep-alive client per serving loop**, opened and closed by the lifespan
   (`infrastructure/llm/jev_http.py`); outside the serving loop a call keeps its own client.
   Every one of the week's 34 production timeouts sat on the 2 s deadline, the cost of a
   fresh DNS/TCP/TLS connection per decision on the production host. Its limits are the
   vendor SDK's own defaults — 100 connections, all kept open for 30 s while idle, so a
   burst reuses them — far above any burst a worker fires, since a decision's deadline
   includes the wait for a connection. It keeps ADR-325's single attempt: the vendor
   documents retrying 429/529, but production showed none in seven days (792 decisions),
   and a request retried after it was sent may be billed twice with one charge recorded.
3. **What the provider asserted is evidence, and some of it is decided in code.** Email
   labels and reply-to (under the unified names), a calendar entry's type, video call and
   recurrence reach the classification; mail the provider filed under promotions, social,
   updates or forums is never published as spam without the spam label, and a birthday,
   focus-time or working-location entry is its category.
4. **Acceptance levels are chosen where they can be measured.** The email and appointment
   floors become 0.80 / 0.80 (from 0.95 / 0.99): no wrong label on any frozen corpus from
   0.50 on jev-1.14.0, first safe level 0.70 across layouts and versions, plus one step of
   margin; a production-shaped corpus goes from 62 % to 86 % coverage with no wrong label.
   The initiative skip becomes p ≤ 0.20 (from 0.11), chosen on the gate corpora rebuilt by
   the product's state builder. This is the established rule applied to the states the
   product actually builds — not a lowered threshold absorbing a regression.
5. **The initiative state names its tools, it does not ship their contracts.** Name, agent
   and description; the evaluator that builds the calls keeps the full catalogue.

The collection-preview question was measured and kept (its three-way shape outperformed a
single relevance Noul); its verdicts still have no consumer, which remains an open product
decision. The radio verifier now counts the scripts it hands back before any call.

**Amendment — 2026-10-26 (every usage on the model it runs):** dev and production run
`jev-1.14.0` since 2026-10-25 while most thresholds were calibrated on 1.13, and the vendor
pins a version wherever thresholds are tuned. Every usage was replayed on 1.14 with its
shipped question, on its committed corpora or, where those were never versioned, on fresh
ones now kept in the [record](../superpowers/qualification/jev-audit-2026-10-25/README.md);
`LLM_DEFAULTS` pins `jev-1.14.0` and the catalogue carries its documented facts. One rule,
fixed before reading: the first level with no wrong decision on every corpus, one step of
margin, the stricter of a tie.

| Usage | On 1.14 | Decision |
|---|---|---|
| Collection previews (8) | dated requests never decided: a relative day needs date arithmetic the rule forbids | the code computes each item's own day (`start`, `received`) in the person's timezone setting; floor kept at 0.94; production-shaped coverage 0.25 → 0.65, no wrong verdict |
| Consultation (both) | a wrong shortcut at 0.97 (an injection case) | raised to 0.98 |
| HITL total refusal | no wrong shortcut at any level; 0.99 kept 4 refusals of 20 | 0.80 (19 of 20) |
| HITL exclusion | no wrong exclusion from 0.80; 0.99 kept 11 of 23 | 0.90 (18 of 23); the scope keeps 0.80 |
| Meeting template | no wrong template from 0.70; 0.95 kept 9 of 19 | 0.85 (17 of 19) |
| Memory reference presence, radio, parameter kind, initiative | no wrong decision at the shipped levels | kept |
| Extraction observers (4) | shadow by design, off in production | unchanged: skipping an extractor would suppress writes, and no labelled corpus exists |

A wrong collection verdict, refusal, exclusion or template stays bounded where it was:
previews remove nothing, exclusions and refusals return to a human confirmation, a template
is reformattable. The shared client keeps the vendor SDK's own pool (100 connections, all
kept 30 s) and the single attempt. A JEV annotation reaches the filtering evidence as its
view, never its instants (ADR-351 amendment 2026-10-26).

## Context

LIA spends model time on decisions which do not require prose: choosing a meeting
template, recognizing a supported consultation, judging relevance or deciding
whether an initiative has anything useful to add. The owner requested an evaluation
of TypeSafe/Jev across these paths, including every searchable collection, with
latency, quality, cost and reversibility considered together. The subsequent lots
were authorized with administrative switches and a readable JEV debug panel.

A fast native decision is not automatically a faster journey. Configuration reads,
accounting, extra observers and a fallback can offset its inference time. Nor does
a concentrated probability distribution prove a decision correct. The integration
therefore needs bounded authority, an existing fallback, attributable spend and
measurements of both individual calls and complete journeys.

The chat pipeline already produces an English query for downstream reasoning.
Evaluating six translated copies of that query would misrepresent this path.
However, retrieved content, radio scripts, meeting transcripts and extraction
contexts retain their own languages. Those inputs cannot be assumed to be English.

This decision extends the existing model catalogue, LLM configuration, cost
tracking, approval and transparency architecture. Operational details and the
functional acceptance procedure live in [JEV integration](../technical/JEV_INTEGRATION.md).

## Decision

### 1. A native decision provider, not a chat adapter

Register `typesafe` as a provider and `decision` as a model kind. Dedicated slots
use the existing encrypted provider credentials, model catalogue, administrative
configuration and text-pricing screens. A decision model cannot occupy a generative
chat slot; generation parameters are refused rather than silently ignored.

Use the native `Choice` transport in
[typesafe_client.py](../../apps/api/src/infrastructure/llm/typesafe_client.py).
The shipped integrations do not invent chat completions around JEV or introduce
unused abstractions for other vendor primitives. Model defaults and the version
pin belong to [LLM_DEFAULTS](../../apps/api/src/domains/llm_config/constants.py),
not to this document. Catalogue facts are declared explicitly when public registry
imports do not cover this provider; runtime never fetches registry data.

Every request supplies bounded state, an explicit question and allowed choices.
Independent questions about the same state may share one bounded batch. Request
bytes, question count, response bytes and deadlines have code-owned limits.
An oversized context causes abstention or fallback; it is not silently shortened
to manufacture a decision. Debug truncation is a separate display concern.

Validate the whole response: expected question identifiers, allowed choices,
finite confidence and probabilities, and the batch's completeness. Invalid,
uncertain, missing or timed-out answers cannot become successful decisions.
There are no implicit transport retries. Provider error bodies are not copied
into logs or diagnostic records.

### 2. One declared usage, one switch and one configuration slot

[jev_registry.py](../../apps/api/src/domains/llm_config/jev_registry.py) is the
authoritative inventory. Each usage declares its setting, slot and translated
label. Completeness tests prevent a new integration from sharing another usage's
switch or being omitted from administration.

**Administration → Intégrations JEV** exposes a general switch and independent
usage switches, initially off. Switching the general control off preserves the
individual preferences. Activation requires usable credentials, an active decision
model and a price. Administrative writes use the existing authorization and audit
mechanisms; the interface confirms only a successful server response.

Each operation reads its routing configuration from PostgreSQL through
[jev_settings.py](../../apps/api/src/domains/llm_config/jev_settings.py) and keeps
an immutable operation snapshot. Later operations observe committed switch
changes across workers without depending on a Redis invalidation message. A
switch does not retroactively cancel an already running call.

### 3. Authority stays narrower than the model's ability to classify

| Integration | What JEV may decide | Boundary and fallback |
| --- | --- | --- |
| Meeting template | Choose among the permitted templates for automatic selection. | Explicit selection and user preference retain precedence. An unusable decision invokes the existing selector. The existing synthesis slot writes the minutes. |
| Email, event, task and file relevance | Qualify already retrieved items for a search preview. | No additional search, permission grant or deletion. Excluded items remain accessible and in the canonical results used for synthesis. Uncertain items remain distinguishable. |
| Reminder, ticket and MCP relevance | Apply the same preview contract to supported structured collections. | Arbitrary external fields remain untrusted evidence. Unsupported or truncated evidence cannot establish irrelevance. |
| Document relevance | Qualify available document excerpts. | An excerpt is not the whole document; absence in an excerpt is not proof of absence from the document. Main RAG context is retained. |
| Radio verification | Judge the script against its cited facts. | Missing references, oversized evidence or an uncertain batch send the original script to the existing verifier. The deterministic editor, rejection rules and verification preferences remain authoritative. |
| Simple consultations | Select an eligible, predefined read-only path after query analysis and catalogue filtering. | No model-generated tool name or free-form arguments. References, ambiguity, unsupported combinations and replans use the existing planner. Validation and execution still use the normal pipeline. |
| Bounded consultations | Select supported paths with explicit bounds such as a local day or quantity. | Code resolves dates, time zones and limits. Unsupported constraints use the planner; a classifier does not perform calendar arithmetic. |
| Initiative utility | Conclude that the full existing initiative context has no useful action, suggestion or follow-up. | Otherwise the existing evaluator runs. Merely finding no action is insufficient. Oversized context uses the existing evaluator. |
| Memory, interests, journal and open-loop observers | Compare a decision with the existing extractor's proposal. | Observation never suppresses extraction or writes. A proposal is not evidence that persistence succeeded. These observers add work and cost. |
| HITL item exclusions | Interpret explicit exclusions from the currently proposed list. | Original item indices remain stable. Any uncertain or invalid batch falls back for the whole list. Exclusion never grants approval; confirmation remains required, and an empty list cancels. |
| Personal-reference presence | Conclude that the query has no personal reference requiring the existing extractor. | Broad memory retrieval remains active. Relations, pronouns, implicit places and uncertainty use the original extraction and resolution. No identity, memory or action is selected. |
| Complete HITL rejection | Recognize an explicit withdrawal of all currently proposed actions. | Partial, conditional or ambiguous replies use the existing classifier. A changed pending list invalidates the decision. This path can only reject, never approve or edit parameters. |

The exact eligible paths, bounds and confidence policies are owned by their
implementations and corpus tests, not by this table. In particular, the
consultation shortcut is a pipeline optimization, not a replacement of ReAct.

Prompts are versioned files under
[the existing prompt directory](../../apps/api/src/domains/agents/prompts/v1).
They name the object being judged and the scope of the evidence. External text is
data, never an instruction to change authorization, tool arguments or policy.
Deterministic identity checks, arithmetic, time handling and permissions remain
in code. A confidence threshold is an acceptance policy, not a correctness guarantee.

### 4. Fallbacks have explicit outcomes and actual costs

[jev_runtime.py](../../apps/api/src/infrastructure/llm/jev_runtime.py) centralizes
configuration, usage-limit enforcement, the native attempt, accounting and its
diagnostic outcome. A disabled or ineligible path makes no paid JEV call.
An unusable native result hands control back to the caller's existing path.

Charge actual provider usage once per native batch, including valid usage returned
with an invalid answer. Price and exchange-rate snapshots follow the existing
cost machinery. A paid attempt and its generative fallback are two real expenses;
neither is hidden by reporting only the eventual successful model.

Attach spend to the matching user and run. Chat-bound work may use its matching
ambient tracker; meeting and background extraction paths retain their own
accounting lifecycle. Cancellation must finish known accounting before propagating.
Preview and observer tasks are cancelled and joined before their owner's tracker
or stream closes; detached work cannot leak into a later turn.

The ephemeral preview travels through SSE and is not conversation history or
checkpoint state. Its diagnostics remain available to administrators while the
intermediate panel is hidden in chat. A relevance result never removes an item
from the canonical registry or changes the final answer's authority.
The user-facing treatment registers continue to describe actual consultations
and actions; the administrative debug feed is not a substitute for those registers.

### 5. Debug explains both the decision and what followed

The JEV section shows caller, bounded context, formatted answer, confidence,
timing, spend and the action/outcome. Human-readable labels are primary;
technical details are expandable. Omitted context is explicitly counted.

Keep **proposed**, **applied**, **pending**, **cancelled** and **fallback requested**
distinct. Requesting a fallback does not prove that the fallback succeeded.
Low-confidence exclusions must remain uncertain in the display. Extraction
observations describe the existing proposal, not a claimed database write.

The per-account feed also exposes background meeting operations independently
of a chat turn. Access is checked on every read against the existing debug
capability and account preference. Data belongs only to the authenticated owner.
Revocation clears the frontend state; responses use `no-store`, the UI does not
persist the feed in browser storage, and polling runs only while the section and
page are visible.

[jev_debug_store.py](../../apps/api/src/infrastructure/llm/jev_debug_store.py)
stores encrypted, bounded records in Redis with expiry per record. Updating an
outcome preserves its original expiry, so ongoing traffic does not keep old
contexts alive. The key family participates in account cleanup. Diagnostic work
is bounded and best-effort and never repeats inference. Ordinary metrics and
logs carry operational metadata, not the private decision context.
The shared runtime logs each completed native attempt with its usage, models,
duration, outcome, available usage and spend. An invalid response includes only
a bounded validation reason; source content, candidate values and response bodies
are never included in that operational event. This separates transport validation
from consumer acceptance while retaining the existing private diagnostic feed.
The same closed validation reason is retained in that feed and shown in the
administrative technical details; older traces default to no reason. No raw
provider-error body is introduced by this field.

### 6. Measure journeys before claiming a latency or quality gain

Keep three separate observations: native call duration, first useful result and
complete response delivery. The server's monotonic journey timing includes
background joins and accounting before completion; it excludes browser rendering
and network transit. Status messages and empty previews are not useful results.

[measure_jev_journeys.py](../../apps/api/scripts/measure_jev_journeys.py) reads an
allowlist of fields and pairs OFF/ON journeys with explicit quality annotations.
Comparison requires equivalent environment, model configuration, input and data.
Missing or duplicate pairs do not establish a gain. Small-sample percentiles are
descriptive, and summed isolated call durations are not measured journey latency.

The replay scripts exercise actual prompt builders and state projections against
synthetic corpora, with independent holdouts where recorded. Their evidence and
limits are in the plans for [lot 1](../superpowers/plans/2026-09-28-jev-lot-1.md),
[lots 2–3](../superpowers/plans/2026-09-29-jev-remaining-lots.md) and
[lots 4–8](../superpowers/plans/2026-09-29-jev-lots-4-8.md).

These measurements support bounded experiments, not a universal replacement of
generative models. In particular, observed HITL call savings do not establish an
end-to-end gain once fallbacks and overhead are included. Collection previews and
extraction observers are additional calls. Radio fallback frequency must be
included in its evaluation. Production activation remains a per-usage decision
after dev acceptance; no switch is enabled merely because tests pass.

The paid synthetic review on 2026-10-04 compared the shipped builders with shorter
questions across the registered usages. The shorter variant was not adopted:
some task and initiative answers passed confidence gates while violating their
functional constraints. The specific HITL scope correction was calibrated on
12 cases and then checked on 24 new cases spanning six languages. It retained
the same nine useful selections and blocked four incorrect admissions; no
ambiguous request was admitted in that holdout. Native HITL cost increased by
15.3%, with median call times of about 229 ms before and 231 ms after. These are
single-observation synthetic results, not production precision or end-to-end
latency measurements. Adding a necessary judgment has a measured cost.

A production aggregate read at 10:30:30 UTC on the same date contained 29 native
calls, including one accounted invalid response. All three native initiative
attempts were followed by the generative initiative evaluator, so this sample
showed no avoided generative initiative call. Collection qualification and
extraction observers remained additional diagnostic work; neither establishes
an observed saving merely because its native answer succeeded.

The subsequent [value and text-billing review](../superpowers/plans/2026-10-04-jev-value-and-text-billing.md)
added the two absence/rejection usages through the existing per-usage switch
mechanism, initially off. The personal-reference holdout blocked seven wrong
generative extractions without a false bypass, but its modeled cost increased
with a warm prompt cache. The rejection experiment avoided five generative calls
on 24 independent cases and reduced that pass's cost while increasing overall
median latency. Neither result establishes a universal saving. Initiative prompt
and format variants were rejected after accounting for their fallbacks. Existing
preferences and diagnostic integrations were preserved.

## Alternatives considered

- **Treat JEV as a general chat model:** rejected; it would obscure the native
  decision contract, expose meaningless parameters and blur the authority boundary.
- **Replace every semantic filter or extractor immediately:** rejected; uncertain
  classifications could silently remove evidence or suppress useful memory.
- **Use only a global switch or deployment-time environment flags:** rejected;
  the owner requires independent, hot comparison and rollback of each usage.
- **Rely on confidence alone:** rejected; distribution concentration does not
  replace task-specific corpora, holdouts or functional acceptance.
- **Claim savings from isolated inference time:** rejected; extra calls, fallbacks
  and accounting affect complete journeys differently.
- **Persist raw diagnostic payloads in general logs:** rejected; private source
  content needs account scoping, encryption, expiry and revocable access.

## Consequences and verification

The integration can be disabled without changing the existing generative paths.
Its additional configuration and accounting code is the cost of making native
decisions independently observable and reversible. Conservative fallback protects
existing behavior but may erase the expected latency or cost benefit.

Tests cover native malformed responses and paid failures, cancellation, quota
refusal, user/run ownership, hot-switch concurrency, database migrations, ledger
entries, debug authorization/expiry, hostile source text and the individual usage
boundaries. Frontend tests cover switches, errors, permission revocation and
readable outcomes. The integration tests under
[tests/integration](../../apps/api/tests/integration) exercise PostgreSQL and Redis
contracts; hermetic UI tests do not prove real provider quality or device behavior.

The replay corpus and dev acceptance must evolve whenever a prompt, eligibility
rule, threshold or model version changes. Existing quality ratchets are maintained;
a lower threshold is not a repair for failing behavior. Future usages must join the
registry, configuration, pricing, accounting, diagnostics and functional tests
before activation. They must retain an explicit abstention outcome and document
whether they replace work, add work or merely observe it.

Operational rollback is the general or per-usage OFF switch. The seed migration
preserves administered data; downgrade is deliberately guarded against deleting
modified models or spend history. PostgreSQL enum values are not removed during
routine rollback. See the
[native-type migration](../../apps/api/alembic/versions/2026_09_28_2100-8bd197e03fa6_jev_native_types.py)
and [seed migration](../../apps/api/alembic/versions/2026_09_28_2101-b138c047a5d2_seed_jev.py).
