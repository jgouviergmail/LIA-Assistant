# ADR-348 — LIA's efficacy is learned from evidence: results and usefulness kept apart, never from its own self-rating

- **Status**: Accepted (pilot)
- **Date**: 2026-10-16
- **Amends**: [ADR-068](ADR-068-Psyche-Engine.md) (layer 5's self-efficacy is no
  longer fed by the self-report and no longer injected as confidence),
  [ADR-104](ADR-104-Psyche-De-Saturation.md) (no pride pulse, no attachment gain
  is ever derived from an efficacy index), [ADR-120](ADR-120-Semantic-Evidence-Expansion-And-Param-Guard.md)
  (amendment 2026-10-11: the turn's efficacy context lives in `query_intelligence`,
  never in a state key of its own), [ADR-336](ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md) (the
  final coverage of the requested outcomes is the result axis' only evidence)
- **Scope**: `domains/psyche/` — `efficacy_contracts.py`, `efficacy_models.py`,
  `efficacy_repository.py`, `efficacy_scoring.py`, `efficacy_policy.py`,
  `efficacy_service.py`, `constants.py` (`EfficacyDomain`, `EFFICACY_WINDOW_DAYS`,
  `EFFICACY_MAX_EPISODES`, `EFFICACY_MIN_SAMPLES`), `service.py`, `router.py`,
  `reset_snapshot.py`; `domains/agents/` — `analysis/efficacy_context.py`, the query
  analyzer's `efficacy_analysis`, `services/efficacy_runtime.py`,
  `efficacy_evidence.py`, `efficacy_provenance.py`, `efficacy_feedback.py`,
  `prompts/v1/psyche_efficacy_directive.txt`, the router, the planner, the ReAct call
  and the response node; `domains/conversations/efficacy_feedback.py` (the injected
  port), `infrastructure/startup/registries.py`; `core/config/psyche.py`
  (`PSYCHE_EFFICACY_COLLECTION_ENABLED`, `PSYCHE_EFFICACY_INFLUENCE_ENABLED`);
  migration `c8d1f4260e77`; the web panel `components/psyche/PsycheEfficacy.tsx`
- **Design study and plan**:
  [`2026-10-16-psyche-efficacy-pilot-design.md`](../superpowers/specs/2026-10-16-psyche-efficacy-pilot-design.md),
  [`2026-10-16-psyche-efficacy-pilot.md`](../superpowers/plans/2026-10-16-psyche-efficacy-pilot.md)

## Context

ADR-068 gave the Psyche Engine a fifth layer of « self-efficacy »: seven domains
(planning, information, emotional support, creativity, technical, social,
organization), each a Bayesian score, with strengths and weaknesses injected into
the response prompt as confidence. Read against the code before anything changed
(2026-10-16), that layer measured none of what its name promised:

| Fact | Consequence |
|---|---|
| Only `emotional_support` was ever updated, from the model's own quality self-rating of the conversation | A technical success could only move the wrong domain, and six domains never moved at all |
| The self-rating prompt capped the quality whenever the person's valence was negative | An emotional signal was read as a competence |
| A first success read 66.7 %, a first failure 33.3 % | One exchange crossed the strength / weakness thresholds |
| The capped weight stayed at 10 after 8 successes as after 100 | The weight was neither an evidence count nor an uncertainty |
| The main format injected weaknesses only, and skipped them on the near-neutral PAD path | The caution depended on the mood, not on the evidence |
| The injection sat in the final answer's preparation | The planner and the ReAct loop — where checking or asking is decided — never read it |
| No write was deduplicated by run, and the JSONB was read then replaced | A replay or two concurrent writes could count twice or lose one |

A self-assessment can be a useful relational signal; it is not evidence that an
answer was right. The decision is what to replace it with, without adding a judge
model to every exchange.

## Decision

### 1. Two axes of evidence, never merged

An **episode** is the logical work of one turn — its run, across SSE segments and
HITL resumptions. It carries at most **two** cognitive domains, attributed by the
query analyzer that already runs (a closed `efficacy_analysis` field; no extra
model call, no keyword classifier; an unknown attribution stays valid and counts
nowhere). Each episode records, separately:

- **the result** — what the final coverage of the requested outcomes (ADR-336)
  verifiably established: `success`, `failure`, `partial`, `unknown` or `excluded`,
  each with a typed reason. A tool's HTTP 200 or a generic success flag is never a
  result. A wait for confirmation, a human refusal, a quota, an absent connector,
  a provider outage or an opaque output is `excluded` — not a cognitive failure; an
  honestly stated limit is not penalised as a false success; a partial is kept as
  partial, never converted into an invented 0.5;
- **the usefulness the owner expressed** — the 👍/👎 given to the turn's canonical
  final message. Silence is no opinion. A question LIA asked, a clarification, a
  session card or a notification does not rate the task. On an episode covering
  two domains the feedback stays a global feedback (`unassigned_feedback_count`)
  and condemns neither domain alone.

The two axes are projected per domain as two indices with their own counts and
dates; nothing averages them into a « competence rate ». The self-report keeps
feeding the relationship and the emotions, and nothing else.

### 2. Bounded, private, corrected in place

Episodes live in `psyche_efficacy_episodes` (migration `c8d1f4260e77`), unique on
(owner, generation, run) and (owner, generation, message), with an immutable
terminal date and a configuration fingerprint as metadata — never as a key that
would count the same episode twice. A 👍 → 👎 → 👍 replaces the feedback rather
than stacking three. The owner lock is taken before the read, and the insert and
the projection share one transaction.

The window is `EFFICACY_WINDOW_DAYS` (90), the ledger holds at most
`EFFICACY_MAX_EPISODES` (500) per owner, and an index exists only from
`EFFICACY_MIN_SAMPLES` (5) observations of its own axis: one exchange can no longer
make a strength or a weakness. Eviction follows the terminal date; after an
eviction by quantity a monotonic bound in the generation's metadata keeps a
replayed finaliser from resurrecting what was evicted.

The legacy scores stay readable and are **not** converted: the profile starts with
no credible index rather than with reconstructed observations. A full psyche reset
starts a new **generation** (old episodes deleted); a soft reset keeps the
experience; the purge and the account deletion remove the episodes, and the account
export carries them. No raw text, address, recipient or tool payload is stored.
Deleting a conversation keeps the learning (USER_LEARNING doctrine); no message
foreign key could silently erase the profile.

### 3. One bounded adjustment, read where the work is decided

After the analysis and before the work, the router reads the relevant domains and
freezes a compact projection — the derived policy, the domains, the generation and
a validity bound — in the turn's `query_intelligence`. One pure function,
`efficacy_policy.choose_policy`, returns **one** adjustment:

- `verify` — the current turn has an evidence gap, the domain's result history is
  weak (or dominated by partial coverage), and an authorised read/check exists in
  the current catalogue and mode, within budget;
- `state_limit` — the same, with no check possible: name the precise unverified
  point;
- `clarify` — the request is ambiguous and the domain's usefulness is weak: ask one
  question about the CURRENT ambiguity;
- `none` — everything else, and the default.

The planner, every ReAct call and the final synthesis read the same policy through
one versioned block (`psyche_efficacy_directive.txt`), revalidated under the owner
lock after a resumption and before the synthesis; a reset, a purge or an expiry
makes the old influence inactive. The present turn's facts always prevail over the
history, and a long series of successes never validates an absent result. The
adjustment changes no model, no tool, no permission, no budget and no HITL; the mood
does not mask it; and introspection is not a check — a model sentence claiming it
verified proves nothing.

### 4. Feedback through a port, switches on both halves

`conversations` reaches the ledger through a port injected at startup, like the
journals' coupling — no import cycle. Collection and influence switch off
independently (`PSYCHE_EFFICACY_COLLECTION_ENABLED`,
`PSYCHE_EFFICACY_INFLUENCE_ENABLED`, both on by default) and both also require the
`PSYCHE` platform capability and the person's own psyche preference; switched off,
the policy is neutral and the legacy proxy is never reactivated.
`PSYCHE_SELF_EFFICACY_PRIOR_WEIGHT` has no reader any more.

### 5. Shown honestly

Settings › LIA's psyche shows, per domain, « no index yet », « learning » or
« observed », with the basis of each axis and its date — never a percentage
presented as accuracy, and no history graph invented from snapshots that never held
the data.

### Scope of the pilot

Ordinary graph turns — the chat and the channels that go through the graph, in
pipeline and ReAct mode — are collected. Routines, peer replies and direct Live
sessions are not: their identity and evidence are not qualified yet, a peer's
appreciation never rates the recipient's assistant, and the normal end of a call is
not a success.

## Consequences

- The seven domains can receive an appropriate signal, keep its provenance and
  produce a useful effect when the context justifies it — which does not mean every
  domain will have evidence soon after installation: emotional support, social and
  creativity depend on explicit feedback.
- A turn can cost one extra authorised read when `verify` fires; it consumes the
  turn's real limits, and an insufficient quota is said, never penalised.
- The response prompt no longer carries the strengths / weaknesses confidence lines;
  LIA no longer hedges on « weak domains » derived from its own mood score.
- Per-turn cost: one indexed read of the profile on a relevant turn and one bounded
  write after the answer; the directive block is designed around 120 tokens for the
  domains concerned only. That figure is a design target, not a measurement.

### Not measured

No OFF / ON comparison on a frozen corpus has been run: **no gain on real exchanges
is claimed**. The window, the minimum of five observations and the policy
thresholds are the pilot's declared starting values, to be qualified on a held-out
corpus (factual errors, requirements met, needless clarifications, verification
coverage, cost and latency, human appreciation kept apart) before they are tuned.

## Alternatives considered

- **Spread the existing self-rating over the seven domains and enrich the prompts.**
  Short, and wrong: self-reward, the wrong domain, no evidence, and an influence
  that is only verbal.
- **A judge model scoring every exchange, and generalised automatic optimisation.**
  Richer strategies, at the price of cost, latency, the judge's own bias and a much
  heavier qualification; reserved for a separate, budgeted experiment.
- **Reuse `PlanPatternLearner` or the evaluation pipeline.** Their keys and signals
  do not carry the same identity or meaning, and a name does not make a production
  call calibrated; the personal calibration stays separate from global plan
  suggestions.
