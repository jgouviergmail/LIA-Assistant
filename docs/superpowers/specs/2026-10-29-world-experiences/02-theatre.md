# Workstream 2 — Difficult-conversation theatre

[Master plan](README.md) · [Contracts](contracts.md) ·
[Decisions](decisions.md) · [Launch prompt](prompts/02-theatre.md)

**Status:** proposed; written and Live are both required outcomes.
**Blocking choices:** D01, D03–D07, D09–D10.

## Job and useful result

“Before a conversation that matters, let me practise what I will say, encounter
credible resistance, and improve a specific passage without involving the real person.”

Example: practise setting a boundary with a colleague. The person chooses an
objective and difficulty, rehearses an opening, receives concrete feedback,
then retries the same difficult moment. The output is a usable formulation and
a better-practised response, not a claim to predict the real counterpart.

## Proposed first-release scope

- Curated templates such as giving feedback, asking for help, negotiating a
  boundary and addressing a disagreement, with bounded customization.
- One simulated counterparty per scene, adjustable resistance, clear practice
  identity and an always-visible stop/pause-to-review control.
- Written practice, then true Live practice on qualified native providers.
- Separate acting and coaching phases. Feedback cites observable passages,
  distinguishes an observation from interpretation, and offers an actionable retry.
- Retry from a selected acknowledged checkpoint as a new attempt, preserving
  scenario/rubric version. Save selected feedback explicitly.
- Explicit export of an edited real-world draft through native workflows.

Deferred under D01: impersonating a real person's private psychology, importing
all personal history, multi-agent ensembles and unbounded improvised tool use.
Simulation never contacts the person being rehearsed.

## Experience loop

1. Set the desired outcome, relationship type and relevant facts voluntarily.
2. Preview modality, scope of context, cost category and stopping controls.
3. Rehearse with the actor; immediate coaching stays opt-in so it does not destroy
   the rehearsal. Difficulty can be reduced without a public score.
4. Move to debrief: inspect a small number of evidenced improvements.
5. Retry one moment, save a useful result, or prepare an editable real draft.

A stage, actor placement and distinct coach view reinforce the transition between
acting and reflection. They should not add navigation friction before a retry.
The user can always tell fictional speech from personal LIA advice.

## Shared training contract to establish

Recommendation: a typed training boundary names owner, scenario/version,
objective, modality, approved context, role, rubric version, current phase,
acknowledged checkpoint, session revision and bounded paid attempts. These are
conceptual fields, not an approved database schema or endpoint contract.

Recommended phases: preparation → active rehearsal → debrief → ended, with
explicit stopped/interrupted outcomes. A retry branches from an acknowledged
checkpoint instead of rewriting the evidence of the original attempt.
Only one producing attempt owns a session revision at a time.

Use a dedicated isolated training service for bounded acting and feedback rather
than the ordinary conversational graph with its action and learning behaviors.
Continue using the central LLM factory, accounting and registers. If a graph is
justified later, its state must remain isolated and follow native serialization
and turn-reset rules. Do not introduce a graph solely to imitate the chat pipeline.

Language must be able to reuse this boundary without depending on the theatre's
feature switch, content or enabled status.

## Live adaptations and release matrix

F08–F09 require more than a new prompt:

- Server-owned scenario context with no implicit personal context.
- No ordinary action tools, real-work delegation or direct relay of rehearsal.
- Transcription, standby flush, timeout, disconnect and end route to training.
- Ordinary Live and telephone behavior remain unchanged by explicit policy.
- Training uses the native account-level Live lease and stop/audio lifecycle.
- The debrief reads only finalized, attributable input. Missing transcript is
  disclosed; it cannot be filled in by model invention.
- User-funded Live provider cost is shown separately from platform-funded
  feedback or any other explicitly requested LIA generation.

Before shipping, complete a matrix for every offered provider, transport and
target device: start, speech/text input, interruption, stop, standby/resume,
expired credential, missing/late transcript, disconnect, account switch and quota
refusal for platform calls. Mark unsupported capabilities unavailable.
A mock demonstrates code behavior, not microphone quality or vendor isolation.

D05 recommends selecting written or Live at start; a deliberate linked retry may
change modality. “Live direct” is not the training mode.

## Acceptance criteria

| ID | Observable pass condition |
|---|---|
| THE-01 | One scenario supports a complete written rehearsal, evidenced debrief and checkpoint retry without entering the ordinary conversation thread. |
| THE-02 | Fictional personal facts and commands do not reach ordinary archive, memory, interests, journal, profile or open-loop extraction, including closing and standby paths. |
| THE-03 | Saying or typing “send this message” inside the scene cannot invoke a real action or ordinary delegated turn, including malicious scenario instructions and direct tool calls. |
| THE-04 | Explicit export produces an editable native draft with selected content only; executing it still requires current native authority and applicable HITL. |
| THE-05 | A replayed request, reconnect, double stop or concurrent tab cannot duplicate a paid attempt, final debrief or external effect; stale revisions cannot overwrite newer state. |
| THE-06 | All platform acting/feedback usage joins the correct owner's native run/decision; personal Live provider expenditure is not charged to platform quota. |
| THE-07 | Quota, rate, duration and output bounds are enforced at the paid boundary; the person can always stop and recover acknowledged work without an automatic paid fallback. |
| THE-08 | Every offered Live combination passes the release matrix; a competing ordinary Live session respects the same account exclusivity. |
| THE-09 | Feedback references available evidence, identifies missing input and separates suggested phrasing from assertions about a real person's mind or future behavior. |
| THE-10 | Raw audio, transient transcript and saved feedback follow the approved retention/export/delete policy; late callbacks cannot resurrect a closed/deleted session. |
| THE-11 | Keyboard/touch/reduced-motion controls distinguish actor and coach, preserve stop access and work in the private native panel. |
| THE-12 | Ordinary chat, browser Live and telephone closing/learning behavior retain their existing regression contracts. |

## Delivery and validation

Deliver an isolated written vertical slice first, then training-specific Live
startup and closing, then provider/device qualification. Do not call the workstream
complete while Live remains a generic prompt experiment.

Measure voluntary retries, usefulness of suggested formulations and user-reported
readiness before/after practice. Model scores are feedback, not validated measures
of a person's social competence. Pass the shared training contract, evidence and
unresolved provider limitations to the language chat.
