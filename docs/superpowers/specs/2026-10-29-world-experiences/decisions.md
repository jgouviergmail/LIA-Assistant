# Shared decisions and owner arbitrations

[Master plan](README.md) · [Contract evidence](contracts.md)

## Status rules

- **Required:** explicitly requested by the owner, or an existing repository
  contract verified in [contracts](contracts.md).
- **Recommended:** a design proposal, not authorization to implement it.
- **Open arbitration:** a product or operating choice for the owner. Silence is
  not approval. A feature chat may refine independent analysis while a choice is
  open, but must not implement the dependent choice as if accepted.
- **Accepted:** only after recording the owner's actual decision, date and scope.

The four selected experiences, written and Live for theatre/language, inline work,
and preservation of native contracts are **required**. All D01–D11 recommendations
below are **open**. No new ADR is approved or numbered by this dossier.

## D01 — First release scope and order

**Recommendation:** focus first, then theatre with both modalities, language with
both modalities, then camps. Focus starts with a deterministic interval, optional
co-presence and private on-demand coaching. Theatre starts with one simulated
counterparty and a short curated set of practical situations. Language starts
with a small set of practical scenes and explicit learning goals. Camps start
with owner-private project continuity over existing Workboard tickets.

**Alternative:** begin with the most visible Live showcase, or build all four in
parallel. This increases unresolved lifecycle, privacy and cross-chat integration
work before a low-cost slice proves the shared contracts.

**Owner decision needed:** approve these first-release boundaries and order, or
name the larger scope that must be included. In particular, multi-actor theatre,
human voice rooms and full collaborative projects are not silently removed from
the long-term vision; they are proposed later increments.

**Blocks:** detailed scope commitment for each brief, not the evidence audit.

## D02 — Who pays for a social experience

**Verified basis:** F03–F06. A shared room does not identify a legitimate payer.

**Recommendation:** each person explicitly requests and pays the platform usage
of their private coaching. Co-presence and deterministic coordination require no
LLM. Do not ship shared paid facilitation in the first focus slice. A future shared
coach must name one consenting payer before dispatch, disclose scope and bounds,
and separately obtain participants' permission to use their shared input.
A room creator cannot consent on everyone else's behalf.

**Alternative:** split a shared call across participants or fund it at instance
level. Neither is the native per-user attribution contract; both require an
explicit billing-policy extension, not a UI convention.

**Blocks:** any shared LLM actor reading multiple people's contributions.

## D03 — Rehearsal versus personal knowledge

**Verified basis:** F07–F09.

**Recommendation:** isolate all fictional speech, scenario context and feedback
from ordinary conversation and automatic personal learning, in writing and Live.
Do not preload memory, psychology, interests, contacts or relationship dossiers
by default. Let the person choose bounded context explicitly. Save approved
pedagogical goals as feature data.

An explicit export of a useful sentence or real next step creates a reviewable
native draft. It does not export the full transcript, auto-update memory or execute
an external action.

**Alternative:** let all rehearsal feed LIA's normal memory. This changes the
meaning of stored personal facts and requires a separate provenance-aware learning
design. A memory flag or prompt is not sufficient protection.

**Blocks:** every simulated model turn, voice transcript and closing path.

## D04 — Live providers and qualification coverage

**Verified basis:** F03, F08, F09 and F11.

**Recommendation:** use true native Live on the user's configured supported
personal provider, with a shared training purpose and isolation contract.
Qualify each provider/transport/device combination actually offered. If a
combination cannot enforce the training boundary, mark training unavailable for
that combination and offer written practice explicitly.

Retain ordinary Live behavior. Do not publish universal provider parity from one
mocked adapter test. A platform-funded voice offering would be a separate cost
and product decision.

**Alternative:** release training Live for one explicitly selected provider first.
This narrows qualification effort but must be visible in availability and must
not be described as support for every existing Live provider.

**Owner decision needed:** approve qualification of all currently offered native
Live providers, or designate the first supported subset. The current dossier
does not choose a paid provider or change credentials.

**Blocks:** the Live release promise, not written rehearsal development.

## D05 — Written/Live continuity

**Recommendation:** choose a modality at session start in the first release;
retain the same scenario definition, objective, feedback rubric and owner.
Allow a deliberate stop/checkpoint and a new linked attempt in another modality.
Do not promise seamless mid-utterance switching. After voice failure, offer
written continuation from the last acknowledged checkpoint without generating
or paying for anything until the user confirms.

**Alternative:** continuous hot switching with exact partial-turn synchronization.
This requires provider-specific interruption, transcript finalization and billing
semantics before the interface can safely offer it.

**Blocks:** modality-switch UX and its persistence contract.

## D06 — Scenario content and model responsibilities

**Recommendation:** begin with curated, versioned scenario templates and bounded
user customization. One actor role per active reply; separate acting from
feedback. Use a common training lifecycle, with distinct theatre and language
rubrics. Configuration owns models; the scenario owns the exercise objective and
difficulty. LLMs interpret speech and produce contextual replies/feedback, while
deterministic code owns timers, lifecycle, permissions and budget boundaries.

**Alternative:** arbitrary generated worlds, multiple autonomous actors and open
tools in every scene. This adds orchestration and safety/accounting ambiguity
before the core benefit is measured.

**Blocks:** the initial content catalogue and model-slot requirements. Actual
slot names and count remain a code-level design task, not a new registry in docs.

## D07 — Retention, replay and progress

**Recommendation:** keep active transcripts only for a short, operator-configured
resume window; propose **24 hours as a new product default to approve**, not an
existing LIA retention value. Purge transcript content after that window. Do not
persist raw audio in LIA by default. Preserve content-free execution/accounting
receipts under their existing native retention rules.

Saving a feedback summary, selected practice items or project outcome is an
explicit user action, with account export/deletion and an independent delete
control. Such saved data can persist until the owner deletes it. No automatic
personal-memory extraction follows. Provide a clear end-session choice to save
the useful result before transient content expires.

**Alternative:** retain full rehearsal transcripts indefinitely, or keep no
resumable transcript. The first increases sensitive storage and lifecycle work;
the second sacrifices interrupted-session recovery and feedback review.

**Owner decision needed:** confirm the proposed resume window, explicit-save
model and whether full replay is required. Provider-side retention is not
established by repository analysis and must not be represented as controlled by
LIA's local purge.

**Blocks:** persistence schema, retention jobs and replay UX.

## D08 — Base-camp collaboration

**Verified basis:** F10 and F12.

**Recommendation:** first release is an owner-private camp referencing native
tickets. Existing peer assignment remains possible through Workboard, with each
reader's existing permissions. A peer receives only what their ticket authorizes;
they do not inherit the camp's other tickets, documents, training or billing.

**Alternative:** a genuinely shared camp with member roles and shared project
resources. That needs an explicit ACL model, invitation/revocation, independent
resource grants and cross-account deletion rules. Sharing a parent ID or room
membership is not sufficient.

**Blocks:** base-camp schema and cross-user UX. If shared projects are essential
to the first release, revise its scope before implementation rather than widening
Workboard visibility opportunistically.

## D09 — Limits and concurrent spend

**Recommendation:** retain native instance/account quotas and failure semantics;
add only the missing, published per-operation bounds (input, output, duration,
attempts and concurrency) needed by each new feature. Use one active producing
attempt per session and the existing account Live claim. Re-check eligibility
before each new paid act. The feature can stop buying new work when blocked;
already incurred usage remains recorded.

This bounds exposure but is **not an exact monetary reservation** across all
concurrent activity on an account. Quotes must say whether cost is estimated.
Limit values and the acceptable exposure envelope must be selected from measured
usage before release, without embedding model prices in code.

**Alternative:** a strict reserved budget shared across all platform callers.
If the owner requires an exact monetary guarantee, extend the central spending
system with atomic reservation/reconciliation and account-wide tests; do not build
a World-only ledger that other calls can bypass.

**Owner decision needed:** accept bounded exposure under native quotas for the
first release, or require the central reservation work first.

**Blocks:** budget guarantees and launch limits.

## D10 — Availability and user control

**Recommendation:** make each product experience independently controllable
through the native capability framework, with modality availability additionally
dependent on current Live credentials and capabilities. Reuse the same policy for
server enforcement and UI. Disabling creation or generation must preserve access
to authorized saved records and deletion/export.

Provide native keyboard/touch entry to an activity without requiring precise
avatar movement. Keep an accessible private panel. Leaving World should not
erase a project, saved practice or an acknowledged focus deadline. Explicit stop,
pause where supported and completion stay visible.

**Alternative:** make World presence the mandatory runtime host of all activity.
This couples useful work to scene connectivity and weakens mobile/accessibility
and recovery behavior.

**Blocks:** operator controls, routing and lifecycle behavior on World exit.

## D11 — Product validation and rollout

**Recommendation:** release each experience behind native capability controls
after its acceptance gates. Measure outcomes with content-free, permission-scoped
events: starting meaningful work, completed intervals, retries after feedback,
communication goals achieved and native ticket results. Collect self-reported
usefulness separately from LLM scores. Avoid public productivity rankings,
compulsory streaks and completion inferred from time spent online.

Start with a bounded pilot; validate whether the spatial version adds value over
the native non-spatial entry. Agree success thresholds before pilot analysis,
using a baseline rather than invented percentages in this document.

**Alternative:** optimize primarily for time in World or number of model turns.
Those can reward distraction and cost while saying little about user benefit.

**Blocks:** release evaluation, not the first implementation plan.

## Decisions to take first

Before focus implementation: D01, D02, D09 and D10; D07 for any persisted content.
Before the training foundation: D03, D05, D06 and D07.
Before Live commitment: D04 plus the training decisions.
Before camp implementation: D08 and the relevant persistence decision.
Before each pilot: D11 and the actual effective limits.

Record accepted choices here with date, rationale, affected briefs and any ADR
amendment needed. An owner acceptance in a later chat must be copied into this
dossier; no chat is a hidden second source of truth.
