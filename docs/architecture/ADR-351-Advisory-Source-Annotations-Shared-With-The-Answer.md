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

## Amendment 2026-10-25 — a state, never an instant

Measured on dev: an appointment classified at 23:05:59Z, valid until 00:05:59Z,
reached the ReAct loop with its raw instants beside a clock reading « 01:05,
Europe/Paris ». The model read 00:05 < 01:05, told the person the classification
had expired while it was valid for another hour, and, applying « an expired
qualification never means safe » to an appointment, warned about its video links.

Exact dates are deterministic (above), so what a model is told of an annotation
is decided by code. One view, `core/classification_projection.classification_view`,
gives the labels, the evidence scope and a state computed when it is shown —
`current` or `expired`. It replaces the annotation in the tool data both modes
read (`model_classifications`, applied where the model's data block is prepared,
voice channels included) and drives the one-line form the response synthesis,
the briefing and the relationship cards read. The display and the cache keep the
whole annotation. The prompts state that the state is the system's and never
inferred from a date, and keep « never means safe » for emails: an appointment's
category only sorts it.

The email priority question receives its reference time in the zone it names,
as the calibration corpora state theirs (`timezone: UTC`). Production used to
send a UTC instant beside the person's zone: a conversion no corpus measured,
which disagrees with the local day around midnight.

## Amendment 2026-10-26 — the filtering evidence too

Measured on dev the day after: a ReAct turn listed emails labelled five seconds
earlier, and the answer called their assessments « périmées ». The response
prompt carried, for every email, `evaluated_at` and `valid_until` in UTC with no
state, beside a clock in Europe/Paris. The path was the filtering evidence
(`display/filter_evidence.py`), which feeds the response's data-for-filtering
block and the collection filters' native state and had been left out of the
amendment above. It now projects an annotation as `classification_view` as well.
`TestEveryModelFacingSerializer` (`tests/unit/core/test_classification_projection.py`)
renders one annotation through every generic serializer a model reads, so a
projection that drops the state fails there.

## Amendment 2026-10-26 (b) — the history reads it when it is shown

Read in the dev logs of the same morning: fourteen ReAct requests still carried
10 to 15 raw `valid_until` each, every one inside an assistant message of the
history (two earlier answers), none in the system block, the tools or the turn's
own results, which carried the state. An answer's model view
(`display/model_history.with_model_view`) archives the answer's data as JSON with
each annotation whole, and every later turn reads it again: the ReAct window, the
response history, the compaction summary and the post-response extractions.

The view stays archived whole; its state is decided when it is **read**.
`model_view_content`, the one door those readers go through, applies
`serialized_classifications` — `model_classifications` over the JSON the
application serialized itself, matching a real key only (inside a JSON string
every quote is escaped, so quoted text never reads as an annotation). Views
archived before the change are read the same way, with no migration. A label
current when the answer was written reads `expired` once its validity
(`JEV_CLASSIFICATION_*_TTL_SECONDS`, by kind) has passed: « an earlier read's
label, not checked again », as the prompts define it.

- **One moment per ReAct turn.** Every call of a turn reads its history at the
  setup's wall clock (`react_start_time`, which a HITL resume keeps): a label
  expiring between two calls would change the history before the turn's own
  reasoning — refused where thinking is bound to the conversation (ADR-306), a
  broken prefix elsewhere. Across turns an archived answer changes once, when its
  labels expire, so the prompt cache is written again from that answer on, once.
- **The token counters read the stored form** (`stored_model_view`): it does not
  change between two reads, so their per-message memo holds — projected on every
  reducer pass, a view of twenty annotated emails cost 174 µs (measured on the
  workstation). A guard pins its readers.
- **The initiative state handed to JEV** carried the turn's registry items whole;
  `canonical_initiative_context` projects every annotation as its view.

`TestEveryModelFacingSerializer` renders through the archived history and the
initiative state too, and `test_react_history_prefix_stability` drives the real
call node over three calls with the clock already past the labels' validity.
