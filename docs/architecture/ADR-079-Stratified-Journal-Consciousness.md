# ADR-079: Stratified Journal Consciousness

## Status

Accepted

## Date

2026-05-06

## Context

The Personal Journals feature ([ADR-057](ADR-057-Personal-Journals.md)) was originally a single-level operational logbook in which the assistant wrote behavioral directives extracted from conversations. [ADR-064](ADR-064-Journal-Analyst-Persona.md) then introduced the analyst persona and the directive format (`WHEN → DO BECAUSE`) to fix a quality crisis (zero `learnings` in prod, massive redundancy, <10% injection rate).

After several months of usage, the journal still suffered from four structural limitations:

1. **The journal was deaf to its own efficacy.** `injection_count` and `last_injected_at` were tracked in the database but never shown to the LLM at write time. The assistant produced directives without knowing whether earlier ones had ever been useful — every consolidation was a write in the dark.

2. **The journal was flat.** Every entry lived at the same level of abstraction. There was no place for raw observations the assistant noticed but couldn't yet turn into directives, no synthesis layer for transversal patterns, and no compiled portrait that summarized "who this user is" — even though the assistant had enough material to produce all three.

3. **The journal was siloed.** Even when present, journal directives were only injected into the response and planner prompts. Notification flows (interest notifications, voice messages, reminders, heartbeat, fallback responses, ReAct setup) ignored them entirely, breaking relational coherence: the same assistant spoke to the user with completely different levels of personalization across channels.

4. **There was no epistemic gradient.** A directive observed once and a directive validated by twenty exchanges had identical weight. This created auto-confirmation loops: a hasty directive injected by the assistant would shape its next response, which would in turn validate the directive at the next extraction — without any signal that the directive had ever actually worked.

## Decision

Transform the journal from "a useful feature" into the assistant's **organ of operational meta-cognition**, structured around four complementary mechanisms:

### 1. Cognitive stratification — four abstraction levels

Each entry now carries a `level` (`L0` / `L1` / `L2` / `L3`):

- **L0** — raw observation, pre-directive. Used when the assistant notices a signal but cannot yet articulate `WHEN → DO BECAUSE`. Open phrasing, ephemeral.
- **L1** — operational directive (the legacy format inherited from ADR-064). The default — most extractions produce L1 entries.
- **L2** — transversal pattern. Synthesis of multiple convergent L1 directives. Produced by consolidation, not extraction.
- **L3** — portrait facet. Living facets of who the user is (traits, current phase, contexts, contradictions, blind spots, evolution). Managed exclusively by consolidation.

Themes (`learnings`, `user_observations`, `self_reflection`, `ideas_analyses`) remain orthogonal to levels and continue to classify entries by nature.

### 2. Epistemic status — confidence + evidence/contradiction counters

Each entry carries `confidence` (`low` | `medium` | `high`) and two counters: `evidence_count` and `contradiction_count`. Counters are incremented atomically by the deferred self-evaluation mechanism (next point) — never written directly by the LLM, eliminating hallucination risk.

The default is `medium` for fresh entries; `low` for hypotheses; `high` after repeated evidence. The LLM may propose promotion or demotion via `update` actions during consolidation.

### 3. Deferred self-evaluation (T → T+1)

At each conversational turn `T`, the IDs of journal entries injected into the prompt are persisted in the LangGraph state (`MessagesState.injected_journal_ids`). At turn `T+1`, the post-response extractor receives these IDs and can observe how the user reacted to the directives that were applied:

- if the user accepted, engaged, or thanked → the LLM proposes `update` with `evidence_outcome="evidence"`
- if the user pushed back, reformulated, or corrected → the LLM proposes `update` with `evidence_outcome="contradiction"`
- if the directive was not relevant → no signal

The service atomically increments the corresponding counter on the entry. **Token cost: zero** — the same extraction LLM call now sees the previous turn's directives in a dedicated prompt section.

Conversation reset (single conversation per user, resettable at any time) is handled gracefully: when `injected_journal_ids` is empty, the section is simply skipped at the next extraction.

### 4. Ambient diffusion — the user-model portrait everywhere

The consolidation now compiles two formats of the user-model portrait in the same LLM call (zero additional cost):

- `journal_portrait_full` (~150-220 tokens) — faceted portrait: traits of fond, current phase, contexts, contradictions, blind spots, evolution. Used by the conversational pipeline.
- `journal_portrait_brief` (~50-70 tokens) — essence in 2-3 sentences. Used by all secondary flows.

A standalone builder `build_journal_user_model_block(user_id, format, flow)` (mirror of `build_psyche_prompt_block`) reads the persisted portrait and returns a ready-to-inject `<UserModelContext>` block. Six secondary flows now inject the brief format: ReAct setup, interest proactive task, reminder notifications, voice service, heartbeat prompts, fallback response (sync + async). The conversational response and planner inject the full format. **Eight flows total** — the same nuanced model of the user is carried wherever LIA speaks.

### 5. Three-lever user correction (no direct portrait edit)

The portrait is a **synthesis voice** — not user-editable directly. Three levers replace direct editing:

- **Lever 1**: edit/delete the underlying L3 source entries (existing CRUD).
- **Lever 2**: feedback signal via `POST /journals/portrait/feedback`. The user signals what is wrong — the comment is persisted as an L0 entry with `source=user_correction` and triggers a synchronous re-consolidation that prioritizes the signal.
- **Lever 3**: manual consolidation via `POST /journals/consolidate` (also exposed as a "Consolidate now" button in Settings).

This preserves the synthesis logic while giving the user real corrective power. The portrait remains a living synthesis, never frozen by manual override.

### 6. Cross-system signal integration (extraction)

At each extraction, the prompt now includes:

- the assistant's own psyche state (`PsycheState.last_appraisal` — mood, valence, dominant emotions) so the journal can ground its directives in the assistant's own affective state at the turn that just ended
- when the user opted in, factual health signals (already supported by ADR-076)
- the directives injected at the previous turn (deferred self-evaluation)

At each consolidation, the prompt additionally includes:

- observed usage patterns (last 7 days message volume + time-of-day distribution — plain SQL, no LLM)
- conversation history when `journal_consolidation_with_history` is enabled

These are factual, never reproduce raw values, and never mention specific topics — they situate the rhythm without violating privacy.

### 7. Observability — Prometheus metrics suite

Eleven new Prometheus metrics expose the journal's health:

- `journal_entries_total{action,theme,source}` — lifecycle counter
- `journal_extraction_duration_seconds{outcome}` — extraction latency histogram
- `journal_zero_injection_age_days` — central effectiveness gauge: average age of entries never injected
- `journal_evidence_total{outcome}` — deferred self-evaluation outcomes
- `journal_consolidation_promotions_total{from_level,to_level}` — level transitions
- `journal_level_distribution{level}` — active entry counts per level
- `journal_dedup_actions_total` — dedup-induced deletes performed at consolidation STEP 1
- `journal_portrait_compile_duration_seconds` — portrait compilation latency
- `journal_portrait_present_total{flow,format}` — portrait diffusion counter
- `journal_portrait_age_hours` — portrait freshness gauge
- `journal_portrait_feedback_total{outcome}` — lever 2 usage counter

## Architecture summary

```
                    ┌─────────────────────────────────────────────┐
                    │   JOURNAL — stratified meta-cognition       │
                    │                                             │
                    │   L0 raw → L1 directive → L2 pattern → L3 portrait facet │
                    │                                             │
                    │   + deferred self-evaluation (T → T+1)      │
                    │   + epistemic status (low/medium/high)      │
                    │   + portrait compiled in 2 formats          │
                    └────┬────────────────┬──────────────────┬────┘
                         │                │                  │
                  reads  │         reads  │           reads  │
                         ↓                ↓                  ↓
                    ┌────────┐      ┌──────────┐      ┌────────────┐
                    │ Psyche │      │ Memory + │      │ Conversation│
                    │  IA    │      │Interests │      │ + health +  │
                    │        │      │          │      │ usage       │
                    └────────┘      └──────────┘      └────────────┘
                                                              │
                  the compiled portrait is then read by everywhere LIA speaks:
                  response · planner · react · voice · reminders · heartbeat ·
                  interest notifications · fallback · briefing
```

## Storage changes

### `journal_entries` (3 new columns)

| Column | Type | Default | Purpose |
|---|---|---|---|
| `confidence` | VARCHAR(10) | `'medium'` | Epistemic status |
| `evidence_count` | INT | 0 | Validations from deferred self-evaluation |
| `contradiction_count` | INT | 0 | Invalidations from deferred self-evaluation |
| `level` | VARCHAR(2) | `'L1'` | Abstraction level (L0/L1/L2/L3) |

Plus `USER_CORRECTION` added to `JournalEntrySource` enum (used by lever 2 feedback).

### `users` (3 new columns)

| Column | Type | Purpose |
|---|---|---|
| `journal_portrait_full` | TEXT NULL | Compiled full portrait (~200 tokens) |
| `journal_portrait_brief` | TEXT NULL | Compiled brief portrait (~60 tokens) |
| `journal_portrait_compiled_at` | TIMESTAMPTZ NULL | Last compilation timestamp |

### `MessagesState` (LangGraph)

| Field | Type | Purpose |
|---|---|---|
| `injected_journal_ids` | `list[str] \| None` | Carries the IDs from turn T to turn T+1 for deferred self-evaluation. |

## Key implementation patterns

### Symmetric to PsycheService

The `build_journal_user_model_block` builder strictly mirrors `PsycheService.build_psyche_prompt_block`: standalone async, own DB session, read-only, graceful degradation, structured logging. This consistency simplifies the mental model — every "ambient signal source" exposes the same interface to downstream flows.

### Anti-hallucination via outcome signaling

The LLM never writes absolute counter values. It only signals an `evidence_outcome` (`evidence` | `contradiction`) and the service atomically increments. Same pattern for level promotions: the LLM signals the new level, the service updates the column AND increments the `journal_consolidation_promotions_total{from,to}` Prometheus counter.

### JSON output format evolution

The consolidation prompt now returns a JSON object rather than an array:

```json
{
  "actions": [...],
  "portrait_full": "...",
  "portrait_brief": "..."
}
```

The parser (`_parse_consolidation_result`) supports both the new object format and the legacy array format for backward compatibility.

## User-facing changes

### Settings → Journaux Personnels

- New section "Comment LIA te perçoit" (the portrait, read-only, full/brief toggle, last compilation date)
- 🚩 "Signaler un problème" button → lever 2 feedback dialog
- 🔄 "Consolider maintenant" button → lever 3 manual consolidation
- Each entry now displays metric badges: confidence dot (low/medium/high color), level (L0/L1/L2/L3), uses count, last_used relative date, evidence/contradiction counters when non-zero
- Editor permits manual override of `confidence` and `level`
- Toggle "Group by Theme | Level" on the entry accordion
- Filter "Show only entries never used"

### GDPR

- The portrait is included in `GET /journals/export` (full + brief + compiled_at)
- `_mark_user_deleted` scrubs the three portrait columns when an account is deleted
- Source entries (including `user_correction`) are purged automatically by the existing CASCADE on `journal_entries`

## Files

### New (5 files)

- `apps/api/src/domains/journals/portrait_builder.py`
- `apps/api/src/infrastructure/observability/metrics_journals.py`
- `apps/api/alembic/versions/2026_05_05_0004-journals_stratified_consciousness.py`
- `docs/architecture/ADR-079-Stratified-Journal-Consciousness.md` (this file)
- Three rewritten prompts: `journal_introspection_prompt.txt`, `journal_consolidation_prompt.txt`, `journal_analyst_persona.txt`

### Modified (~25 files)

- `apps/api/src/domains/journals/{models,schemas,service,repository,extraction_service,consolidation_service,context_builder,router}.py`
- `apps/api/src/domains/auth/models.py` (3 portrait columns)
- `apps/api/src/domains/agents/models.py` (`injected_journal_ids` in `MessagesState`)
- `apps/api/src/domains/agents/nodes/{response_node,planner_node_v3,react_nodes}.py`
- `apps/api/src/domains/agents/services/fallback_response.py`
- `apps/api/src/domains/voice/service.py`, `apps/api/src/domains/heartbeat/prompts.py`
- `apps/api/src/domains/interests/proactive_task.py`
- `apps/api/src/infrastructure/scheduler/{reminder_notification,journal_consolidation}.py`
- `apps/api/src/domains/users/account_deletion_service.py` (RGPD scrub portrait)
- `apps/web/src/hooks/useJournals.ts`, `apps/web/src/components/settings/JournalsSettings.tsx`
- `apps/web/src/lib/constants.ts` (configurable consolidation timeout)
- `apps/web/locales/{en,fr,de,es,it,zh}/translation.json` (38 new keys × 6)
- `.env.example`, `.env.prod.example` (new `NEXT_PUBLIC_JOURNAL_CONSOLIDATION_TIMEOUT_MS`)

## Consequences

- **Token cost**: ~+200 tokens per main conversation turn (full portrait), ~+60 tokens for secondary flows (brief portrait). Extraction prompt grows by ~500 tokens (visible metrics + previous-turn directives + inner state). Consolidation grows by ~250 tokens (object format with portraits + usage patterns). Soutenable, mesurable.
- **Latency**: +1ms per flow that injects the portrait (one SQL read on `users`). Negligible.
- **Cognitive depth**: the journal can now express observations across four levels of abstraction, with epistemic awareness of its own validation state. The assistant builds genuine understanding of the user over time — measurable via the Prometheus suite.
- **Coherence across channels**: the portrait diffusion ensures that LIA's understanding of the user is consistent in conversations, notifications, voice, reminders, etc. — instead of being a feature of the conversational flow only.
- **Backward compatibility**: existing entries default to `level=L1`, `confidence=medium`, evidence/contradiction counters at 0. No data migration or purge.
- **Existing patterns preserved**: anti-hallucination guards (3 layers from ADR-057), analyst persona (ADR-064), Gemini dual-vector embeddings (ADR-069). Extended, not replaced.

## Alternatives Considered

1. **Direct portrait editing** by the user: rejected. Freezing user-edited content breaks the "synthesis" logic — the next consolidation would either ignore the user's input (frustration) or overwrite it (loss). The three-lever model preserves the synthesis voice while giving the user real corrective power.

2. **Single portrait format** (full only): rejected. Notification flows have tight token budgets — injecting 200 tokens of portrait everywhere would quickly become unsustainable. Two formats with tiering (full for conversation, brief elsewhere) keeps the diffusion frugal.

3. **Synchronous evaluation at turn T** (instead of deferred T → T+1): rejected. Evaluating directives at the same turn they're applied would require a second LLM call per turn, doubling the post-response cost. Deferred evaluation reuses the existing extraction call — zero token overhead.

4. **Persistent override flag on the portrait** (override_until timestamp): rejected. Considered as the original design, but conflicts with the synthesis logic — see alternative 1. Lever 2 (feedback that triggers re-consolidation) achieves the same user power without the synchronization issue.

5. **Hardcoded promotion rules** (e.g. "if 3+ entries on same topic → auto-create L2"): rejected. Loses the LLM's contextual judgment about what counts as "same topic" or "convergent". Prompt-driven promotion (with active scan instructions in STEP 5 of the consolidation prompt) maintains the assistant's autonomy.

## Amendment 2026-09-17 — the diagram's claim becomes true (ADR-292)

The architecture summary above says the journal « reads Memory + Interests ».
It never did: the consolidation prompt received the entries, an optional
slice of the conversation, the usage patterns and the health signals, and
nothing of the memories, the interests, the habits or the relationship
debriefs. ADR-292 makes the claim true through a seam the four sources
install their readers into, adds their four sections to the prompt's INPUTS
as MATERIAL for the synthesis (the doctrine of STEP 7 stands: posture and
cognition, never a fact list), persists the portrait's provenance beside its
words, reopens the account's eligibility when a source moves, and turns the
« ~150-220 » / « ~50-70 tokens » written in prose since this ADR into two
settings the prompt reads (ADR-184).

## Amendment 2026-10-07 — evidence versions and faithful consolidation

The functional audit reproduced independent failures: a late human restriction
was cut from extraction, stale ORM counters lost concurrent reactions, editing a
rule retained its old validation, deleting its final source retained the portrait,
and successful completion swallowed edits made during a model call. Real model
replays also turned a film-date verification method into a cinema interest and
replaced two conditional choice rules with an unsupported permanent identity.

The implementation now enforces these contracts in code:

- Extraction retains the complete latest human message, admits conversation
  writes only at L0/L1, and checks the actual previous exposure's rule revision.
  A consent revision is checked before context, before model work and at settlement.
- Independent outcomes are uniquely recorded in `journal_evidence_events` for
  their rule revision. A semantic change (content, theme or level) starts a new
  validation history. Exposure is not evidence; whole-answer positive feedback
  remains descriptive reception and cannot alone certify a rule.
- Consolidation uses one expiring per-account lease for manual and scheduled
  calls. It captures journal/consent/source identities before model work and
  checks them again under the owner lock. Provider work is prepared outside that
  lock; maintenance, portrait and successful watermark commit together. Invalid,
  failed and stale attempts consume pacing, never the successful revision.
- A merge is an explicit operation over equivalent complete propositions at
  the same theme and level. It unions reaction identities and provenance, and
  refuses a merge that cannot preserve historical evidence.
- The portrait is now a bounded **selection of complete, verified source
  passages**, rather than unchecked free prose. This deliberately supersedes
  the earlier instruction to paraphrase every source and never quote it.
  Conditions, exception clauses, dates and uncertainty remain attached. The model
  chooses relevant passages; code verifies and packs them under the application
  token proxy. No additional model call is required. The brief format may be
  empty if no complete passage fits.
- Source identity includes gates, every row's identity/version, deletions,
  source budgets and naturally expiring local-day material. Ambient consumers
  and the portrait endpoint refuse invalid lineage. Contradiction and semantic
  edits invalidate immediately; confirming evidence preserves already-current
  selected words while making maintenance eligible.
- The shared builders enforce effective permission, whole rendered budgets and
  operational qualification. Native Live and telephone SELF reuse the bounded
  portrait; third-party telephone recipients receive no owner portrait.

The migration preserves descriptive counters and exposure history, demotes
uncorroborated legacy high confidence and invalidates unversioned portraits.
Source identity distinguishes semantic evidence from exposure bookkeeping.
Canonical all-row fingerprints retain non-maximal edits and deletions, while
access/notification timestamps cannot blank an otherwise current portrait.
Memory ranking additionally binds the ordered selected IDs, so a genuine
usage-driven page change remains stale. Habits bind both their mirror rows
and the consumed rhythm profile; an unchanged nightly recompute does not
create new evidence merely by moving its timestamp.

PostgreSQL acceptance tests cover concurrency, revision checks, replay,
rollback, source deletion, consent withdrawal and migration round trips.
Finite tests do not establish longitudinal learning benefit: selection relevance,
cross-entry semantic convergence and answer usefulness still require measured
evaluation on representative conversations. See the current
[technical reference](../technical/JOURNALS.md) for runtime seams and controls.

## Corrective amendment 2026-10-07 — restore the portrait's synthesis voice

The extractive portrait choice recorded in the preceding amendment was a
product regression. "How LIA sees you" became copied memory facts, source and
category labels, interest weights and operational `WHEN -> DO` rules. Exact
source quotations avoided unsupported paraphrases but removed the synthesis
that this ADR and ADR-292 require. The settings card correctly displayed the
API words; removing labels or hiding facts in that card would leave the wrong
portrait in every other flow. The extractive publication contract is therefore
superseded by this correction.

The full portrait again expresses supported cognitive posture, current phase
or focus, relevant contexts and relationships as facets, known rhythm,
observed tensions and open questions in natural prose from the assistant's
perspective. The brief carries the useful posture, focus and interaction
essence. Both use the account's language and admit complete synthesized text
under the existing budgets. Missing facets remain absent. Raw names, dates,
rosters, metrics, source labels and copied directives are evidence for the
reasoning, not its visible portrait. A narrowly scoped email-control request
cannot become an enduring need for control or a recurrent habit inferred from
one instance; provisional inferences remain cautious in natural language.

Generation returns structured claims with a facet, natural text, snapshot-bound
source-item identifiers and brief eligibility. The server resolves each identifier
to its canonical complete internal support passage; the model no longer recopies
source punctuation and metadata. The prompt omits source items that cannot pass
the completeness gate. Legacy exact quotes remain readable but cannot be combined
with an identifier in the same support. Structural source checks establish
traceability and current authorization. Journal supports cannot be created or
mutated by the same maintenance batch, including merge winners and losers.
Those checks still do not prove that a paraphrase preserves its sources'
meaning, conditions or scope.

Actual maintenance mutations nominate a subsequent paced portrait pass through
provenance `portrait_pending`, while their successful watermark still consumes
the writes. That later pass can cite the corrected current material. Omitted
portrait claims keep outstanding work pending; an explicit proposal, including
an empty list, consumes it when no actual maintenance remains. A cosmetic no-op
does not reopen eligibility or erase an already-current portrait, and an
already-reviewed portrait supported by unchanged material may remain current
while the follow-up is pending. This is a separate operation, not a reprompt
within the original generation.

Nonempty budget-admitted claims therefore receive an independent bounded
semantic review through the same configured `journal_consolidation` slot and
account operation. Exact passages are sent once in a proof registry; the entire
request must fit the domain review-input ceiling and half the effective model
context before provider work. The verifier checks support, scope, style and uncertainty
for each independently readable claim. A complete typed response selects the claims
approved on every criterion; refused claims are omitted. A malformed, incomplete or
truncated verdict, or a verdict approving no claim, rejects the operation and
preserves an already-current portrait. Selection makes no additional model call or
application-level retry. The existing provider retry bounds remain.
Empty or maintenance-only proposals need no review. This changes the
earlier zero-additional-call assertion: proposing a portrait now incurs
conditional verification work, attributed alongside generation even when a
later phase fails. Known paid partial failures remain accounted for. Consent,
source identities and usage limits are rechecked before that spend. The receipt
binds both the complete reviewed candidate and the approved publication, including
their wording, exact proofs, brief membership and compiler policy; both are
rechecked at atomic publication.

This partial-publication correction addresses the repeated development failure
observed with an empty journal on 2026-10-07: authorized memories and interests
produced usable claims, but one refused claim vetoed all approved paragraphs.
The selection is over the original budget-admitted candidate, not the generator's
unfiltered list. Removing claims cannot refill a budget slot, promote a paragraph
into the brief or introduce unchecked text. Each paragraph must retain its own
subject, conditions and scope when another paragraph is removed. A wholly refused
candidate is never converted into an empty proposal that clears the old portrait.

Compiler-policy identity participates in the canonical source state. Stored
extractive and unversioned portraits are omitted and nominated for actual
recompilation; unchanged source rows cannot keep the old rendering current.
Changing source eligibility or its proof protocol also changes that identity.
No-output settlement cannot stamp new-policy provenance onto old words. The
source budgets, separate provenance display, revision-bound evidence,
consent/lease fences and atomic maintenance settlement remain in force.

Semantic review is a separate judgment by the same configured model, not a
statistically independent oracle or a deterministic proof of psychological
truth or long-term usefulness. Qualification must include
natural-output cases and scope-preserving paraphrases, alongside the SQL and
revision invariants. See the [technical reference](../technical/JOURNALS.md)
for the current runtime contract and attribution.

## References

- [ADR-057: Personal Journals](ADR-057-Personal-Journals.md) — original design
- [ADR-064: Journal Analyst Persona](ADR-064-Journal-Analyst-Persona.md) — quality crisis fix
- [ADR-069: Gemini Embedding Migration](ADR-069-Gemini-Embedding-Migration.md) — dual-vector
- [ADR-076: Health Metrics Ingestion](ADR-076-Health-Metrics-Ingestion.md) — health signal opt-in
- `docs/technical/JOURNALS.md` — operational reference
