# ADR-351: Advisory source annotations shared with the answer

**Status:** Accepted

**Date:** 2026-10-19

## Context

Email and appointment displays need useful categories, and emails need one
priority level. The assistant must receive the same accepted assessment as the
reader. Provider folders or importance flags alone cannot supply this semantic
judgment, and an inferred label must never authorize an action or certify safety.

## Decision

Register independently switchable native JEV usages under
[ADR-325](ADR-325-JEV-Bounded-Decisions-With-Hot-Switches-And-Accounted-Fallbacks.md),
off by default. Classify the authorized, selected and formatted evidence once,
with its explicit scope, reference time and timezone. Email category and
priority are independent judgments; appointment category is separate. Unknown
decisions remain unlabelled; normal email priority reaches the assistant while
remaining visually quiet. Phishing/scam is a category with a prominent red badge,
bounded attention animation and static reduced-motion rendering.

Use closed annotations with validity and a shared publication policy for the
UI, response synthesis and other authorized display surfaces. Cache identity
includes owner, account binding, revision/occurrence, evidence, model, prompts,
policy, numerical contract and time context. Bounded Redis claims coalesce
overlapping work. Failures, quota limits, cancellation and oversized evidence
preserve the source result without an invented label or generative fallback.
Historical displays keep their captured annotations and never spend on replay.

All usages share the native precision-aware Choice validator. The approximate
mass allowed by the provider is checked against feasible rounding intervals;
raw probabilities are preserved, and missing mass never raises confidence.
Malformed responses remain atomic failures and retain known bills.

Question design distinguishes a reported situation from its authentication,
and an actual deceptive solicitation from a security topic or unethical
advertising. Business thresholds are not lowered to obtain coverage.

## Consequences and verification

Annotations are advisory. A missing badge says nothing about safety, and a
phishing badge is not proof of fraud. Context, permissions, exact dates and
execution remain deterministic. No new LangGraph state field is introduced.

The [guide](../technical/EMAIL_EVENT_CLASSIFICATION.md) describes limits,
accounting and publication. The
[native qualification record](../superpowers/qualification/jev-classification-2026-10-19/README.md)
retains failed candidates, fixed corpora, post-freeze adversarial cases and
real service/cache accounting. The tests bind this evidence to the shipped
policy; it is bounded regression evidence, not population accuracy.
