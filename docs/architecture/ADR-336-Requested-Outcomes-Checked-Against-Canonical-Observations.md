# ADR-336 — Requested outcomes checked against canonical observations

**Status:** Accepted — implemented and qualified locally; deployment is not certified.
**Date:** 2026-10-07
**Deciders:** The owner authorized factual simulations and semantic improvements;
Codex recorded the implementation choices and their measured limits.
**Scope:** Query analysis, tool observations, ReAct recovery, checkpoints and final synthesis.

**Amends:** [ADR-310](ADR-310-ReAct-Turn-Judged-On-Its-Result.md),
[ADR-303](ADR-303-Tool-Failure-Restitution.md) and
[ADR-184](ADR-184-Published-Bounds-And-Non-Prescriptive-Verdicts.md).

## Context and problem statement

ADR-310 allows bounded recovery when the loop declares an unresolved fact. Its
truthfulness still depends on the model identifying its own gap. A successful
tool response can describe the wrong date, an incomplete list or a prepared
draft while the final text claims the user's request was completed. A delegated
MCP report does not expose enough canonical observations to prove each action
that an inner assistant says it performed.

These are different states from a transport failure. The assistant needs an
independent record of the explicit requested results and of what the tools
actually established, while avoiding another verifier model on every turn.

## Decision

1. **Extract explicit obligations from the current request.** The analyzer
   supplies structured requested outcomes with literal source anchors and
   constraints such as operation, exact field value, count, date and same-item
   matching. The application validates those anchors against the person's
   actual current query. An analyzer inference is not a new user obligation.
   Extraction remains model-dependent: an omitted or misunderstood obligation
   cannot be certified by this mechanism.
2. **Anchor relative dates on the server.** The request day and timezone are
   captured for the turn and retained through checkpoint/resume. Civil dates
   preserve their calendar day; timestamps with offsets are compared in the
   request timezone. A resume on a later day must not change what “tomorrow”
   meant. An unreadable or malformed date does not corroborate a date prefix.
3. **Observe canonical outputs before model projection.** Available tool
   identity, arguments, explicit success and completeness markers, and actual
   structured data produce the evidence. A pending confirmation stays pending;
   an opaque or delegated result stays unknown. MCP safety annotations do not
   prove an action verb. Incompleteness in metadata overrides a completion claim
   in data, and lack of a cursor alone does not prove exhaustive retrieval.
4. **Judge the requested constraint, not textual similarity.** Exact supported
   scalar values, full lexical boundaries and same-item constraints prevent a name,
   decimal, mailbox or URL prefix from satisfying a different requested value.
   Scalar matching currently compares string representations, so a numeric value
   and its identical textual representation are not distinguished. Counting
   across pages would require verified identity and page-chain evidence; that
   pagination proof is not implemented. Independent observations remain unknown
   when only their unverified sum could satisfy the requested minimum.
   The status vocabulary distinguishes satisfied, missing, failed, partial,
   pending confirmation and unknown. Unknown is not a success or permission to
   infer hidden execution.
5. **Keep compact evidence in state.** Constraint-specific verdicts and observed
   counts travel through JSON-compatible checkpoint state instead of duplicating
   entire raw tool payloads. This is an outcome ledger, not a second data
   registry or a replacement for effect accounting.
6. **Canonical gaps also reach recovery and final synthesis.** Missing, failed
   or partial requested results can activate the existing bounded recovery
   mechanism even if the model omitted its `<unresolved>` declaration. Recovery
   stays read-only and cannot replay a mutation or an opaque delegation to
   establish a result. Pending and unknown states retain their distinct
   meaning. Final synthesis receives the verified coverage and gaps, with the
   existing budget exits and stop predicate still controlling execution.

The source-level proof boundary is
[ADR-335](ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md).
This decision strengthens the result checks in ADR-310; it retains that ADR's
transient recovery instructions, complete replacement answer and draft fallback.

## Considered options and trade-offs

| Option | Benefit | Reason for the decision |
|---|---|---|
| Trust the final reply or model-declared gaps | No extra application state | A model can omit a gap or mistake a draft for an executed action |
| Add a verifier model after every turn | Flexible natural-language assessment | Additional latency/cost and another probabilistic claim without stronger source evidence |
| Persist complete tool payloads in another ledger | Easy later reinspection | Duplicates the registry and expands checkpoints and prompts |
| Anchored obligations with compact canonical verdicts | Independent, reproducible checks of supported constraints | Selected; bounded by extraction quality and the explicit tool contracts |

## Consequences

The assistant can distinguish useful partial work from false completion and
carry a verified gap into an honest answer. Conservative unknown states can
leave a request unresolved even when an external assistant claims success.
No instruction to recover authorizes another write, overrides HITL or expands
the person's request. More exact checks do not make an extraction model
deterministic or certify external provider accuracy.

## Validation and follow-up

The [execution qualification](../technical/SEMANTIC_EVOLUTION_QUALIFICATION.md)
records result, delegation, lexical and date oracles, as well as the bounded
real-model comparison. The [recorded component observations](../superpowers/qualification/semantic-components-2026-10-06.json)
retain the measured counterexamples.

Representative tests cover
[requested outcomes](../../apps/api/tests/unit/domains/agents/semantic/test_requested_outcomes.py)
and [delegated evidence](../../apps/api/tests/unit/domains/agents/semantic/test_delegated_outcome_evidence.py).
Extend supported constraints only with both a satisfying canonical observation
and a near-match that must remain unsatisfied. Future production evaluation
must separately measure extraction omissions and actual end-to-end completion.

## Implementation references

- [Requested outcome contracts](../../apps/api/src/domains/agents/analysis/requested_outcomes.py)
- [Canonical observation and coverage](../../apps/api/src/domains/agents/services/outcome_evidence.py)
- [Final synthesis directive](../../apps/api/src/domains/agents/services/outcome_directive.py)
- [Observed ReAct gaps](../../apps/api/src/domains/agents/nodes/react_observed_gaps.py)
