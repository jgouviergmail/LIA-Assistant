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

## Owner acceptance — 2026-11-03

The owner explicitly confirmed: “Je valide tes recommandations,” and requested
the dossier update and a complete launch prompt for detailed focus-lounge framing,
strictly inline and without business code.

**D01–D11 are accepted as stated below.** This adopts the recommended options,
not their alternatives. The four experiences, written and Live for theatre and
language, and preservation of native contracts remain required. The delivery
order and first-release scope are now the approved baseline; do not ask the owner
to approve them again merely because work starts in another chat.

This is product and architectural-direction acceptance, not implementation
authorization or runtime qualification. The current scope is analysis and
documentation only: no business code, commit, push or deployment. No new ADR is
numbered here. Detailed schemas, interfaces, limit values and qualification
evidence still have to be designed or established against current code.

The source audit remains dated 2026-10-29. Recording this acceptance does not
revalidate that audit against later repository or deployed changes.

## D01 — First release scope and order

**Accepted decision (2026-11-03):** focus first, then theatre with both modalities, language with
both modalities, then camps. Focus starts with a deterministic interval, optional
co-presence and private on-demand coaching. Theatre starts with one simulated
counterparty and a short curated set of practical situations. Language starts
with a small set of practical scenes and explicit learning goals. Camps start
with owner-private project continuity over existing Workboard tickets.

**Alternative considered — not selected:** begin with the most visible Live showcase, or build all four in
parallel. This increases unresolved lifecycle, privacy and cross-chat integration
work before a low-cost slice proves the shared contracts.

**Confirmed scope:** multi-actor theatre, human voice rooms and full collaborative
projects are deferred from the first release; they remain possible later increments.

**Applies to:** detailed scope commitment for each brief, not the evidence audit.

## D02 — Who pays for a social experience

**Verified basis:** F03–F06. A shared room does not identify a legitimate payer.

**Accepted decision (2026-11-03):** each person explicitly requests and pays the platform usage
of their private coaching. Co-presence and deterministic coordination require no
LLM. Do not ship shared paid facilitation in the first focus slice. A future shared
coach must name one consenting payer before dispatch, disclose scope and bounds,
and separately obtain participants' permission to use their shared input.
A room creator cannot consent on everyone else's behalf.

**Alternative considered — not selected:** split a shared call across participants or fund it at instance
level. Neither is the native per-user attribution contract; both require an
explicit billing-policy extension, not a UI convention.

**Applies to:** any shared LLM actor reading multiple people's contributions.

## D03 — Rehearsal versus personal knowledge

**Verified basis:** F07–F09.

**Accepted decision (2026-11-03):** isolate all fictional speech, scenario context and feedback
from ordinary conversation and automatic personal learning, in writing and Live.
Do not preload memory, psychology, interests, contacts or relationship dossiers
by default. Let the person choose bounded context explicitly. Save approved
pedagogical goals as feature data.

An explicit export of a useful sentence or real next step creates a reviewable
native draft. It does not export the full transcript, auto-update memory or execute
an external action.

**Alternative considered — not selected:** let all rehearsal feed LIA's normal memory. This changes the
meaning of stored personal facts and requires a separate provenance-aware learning
design. A memory flag or prompt is not sufficient protection.

**Applies to:** every simulated model turn, voice transcript and closing path.

## D04 — Live providers and qualification coverage

**Verified basis:** F03, F08, F09 and F11.

**Accepted decision (2026-11-03):** use true native Live on the user's configured supported
personal provider, with a shared training purpose and isolation contract.
Qualify each provider/transport/device combination actually offered. If a
combination cannot enforce the training boundary, mark training unavailable for
that combination and offer written practice explicitly.

Retain ordinary Live behavior. Do not publish universal provider parity from one
mocked adapter test. A platform-funded voice offering would be a separate cost
and product decision.

**Alternative considered — not selected:** release training Live for one explicitly selected provider first.
This narrows qualification effort but must be visible in availability and must
not be described as support for every existing Live provider.

**Confirmed coverage:** qualify all currently offered native Live providers
against the training contract. Each offered provider/transport/device combination
must have evidence; combinations that cannot enforce the contract stay unavailable
for training. This does not select a new paid provider or change credentials.

**Applies to:** the Live release promise, not written rehearsal development.

## D05 — Written/Live continuity

**Accepted decision (2026-11-03):** choose a modality at session start in the first release;
retain the same scenario definition, objective, feedback rubric and owner.
Allow a deliberate stop/checkpoint and a new linked attempt in another modality.
Do not promise seamless mid-utterance switching. After voice failure, offer
written continuation from the last acknowledged checkpoint without generating
or paying for anything until the user confirms.

**Alternative considered — not selected:** continuous hot switching with exact partial-turn synchronization.
This requires provider-specific interruption, transcript finalization and billing
semantics before the interface can safely offer it.

**Applies to:** modality-switch UX and its persistence contract.

## D06 — Scenario content and model responsibilities

**Accepted decision (2026-11-03):** begin with curated, versioned scenario templates and bounded
user customization. One actor role per active reply; separate acting from
feedback. Use a common training lifecycle, with distinct theatre and language
rubrics. Configuration owns models; the scenario owns the exercise objective and
difficulty. LLMs interpret speech and produce contextual replies/feedback, while
deterministic code owns timers, lifecycle, permissions and budget boundaries.

**Alternative considered — not selected:** arbitrary generated worlds, multiple autonomous actors and open
tools in every scene. This adds orchestration and safety/accounting ambiguity
before the core benefit is measured.

**Applies to:** the initial content catalogue and model-slot requirements. Actual
slot names and count remain a code-level design task, not a new registry in docs.

## D07 — Retention, replay and progress

**Accepted decision (2026-11-03):** keep active transcripts only for a short, operator-configured
resume window with **24 hours as the accepted new product default**, not a
claim about an existing LIA retention value. Purge transcript content after that
window. Do not persist raw audio in LIA by default. Preserve content-free execution/accounting
receipts under their existing native retention rules.

Saving a feedback summary, selected practice items or project outcome is an
explicit user action, with account export/deletion and an independent delete
control. Such saved data can persist until the owner deletes it. No automatic
personal-memory extraction follows. Provide a clear end-session choice to save
the useful result before transient content expires.

**Alternative considered — not selected:** retain full rehearsal transcripts indefinitely, or keep no
resumable transcript. The first increases sensitive storage and lifecycle work;
the second sacrifices interrupted-session recovery and feedback review.

**Confirmed scope:** the resume window and explicit-save model are accepted;
indefinite full-transcript replay is not part of the first release. Provider-side
retention is not established by repository analysis and must not be represented
as controlled by LIA's local purge.

**Detailed design still needed:** identify the transient resources to which this
window applies, its clock anchor and deletion/recovery behavior. Do not apply it
to native accounting receipts or explicitly saved outcomes.

**Applies to:** persistence schema, retention jobs and replay UX.

## D08 — Base-camp collaboration

**Verified basis:** F10 and F12.

**Accepted decision (2026-11-03):** first release is an owner-private camp referencing native
tickets. Existing peer assignment remains possible through Workboard, with each
reader's existing permissions. A peer receives only what their ticket authorizes;
they do not inherit the camp's other tickets, documents, training or billing.

**Alternative considered — not selected:** a genuinely shared camp with member roles and shared project
resources. That needs an explicit ACL model, invitation/revocation, independent
resource grants and cross-account deletion rules. Sharing a parent ID or room
membership is not sufficient.

**Applies to:** base-camp schema and cross-user UX. A later move to genuinely
shared projects requires an explicit scope revision; do not widen Workboard
visibility opportunistically.

## D09 — Limits and concurrent spend

**Accepted decision (2026-11-03):** retain native instance/account quotas and failure semantics;
add only the missing, published per-operation bounds (input, output, duration,
attempts and concurrency) needed by each new feature. Use one active producing
attempt per session and the existing account Live claim. Re-check eligibility
before each new paid act. The feature can stop buying new work when blocked;
already incurred usage remains recorded.

This bounds exposure but is **not an exact monetary reservation** across all
concurrent activity on an account. Quotes must say whether cost is estimated.
Limit values and the acceptable exposure envelope must be selected from measured
usage before release, without embedding model prices in code.

**Alternative considered — not selected:** a strict reserved budget shared across all platform callers.
If the owner requires an exact monetary guarantee, extend the central spending
system with atomic reservation/reconciliation and account-wide tests; do not build
a World-only ledger that other calls can bypass.

**Confirmed budget policy:** bounded exposure under native quotas is accepted for
the first release. A central atomic monetary-reservation system is not a
prerequisite and must not be introduced as implied scope. Actual limit values
still require a source-backed proposal and qualification before release.

**Applies to:** budget guarantees and launch limits.

## D10 — Availability and user control

**Accepted decision (2026-11-03):** make each product experience independently controllable
through the native capability framework, with modality availability additionally
dependent on current Live credentials and capabilities. Reuse the same policy for
server enforcement and UI. Disabling creation or generation must preserve access
to authorized saved records and deletion/export.

Provide native keyboard/touch entry to an activity without requiring precise
avatar movement. Keep an accessible private panel. Leaving World should not
erase a project, saved practice or an acknowledged focus deadline. Explicit stop,
pause where supported and completion stay visible.

**Alternative considered — not selected:** make World presence the mandatory runtime host of all activity.
This couples useful work to scene connectivity and weakens mobile/accessibility
and recovery behavior.

**Applies to:** operator controls, routing and lifecycle behavior on World exit.

## D11 — Product validation and rollout

**Accepted decision (2026-11-03):** release each experience behind native capability controls
after its acceptance gates. Measure outcomes with content-free, permission-scoped
events: starting meaningful work, completed intervals, retries after feedback,
communication goals achieved and native ticket results. Collect self-reported
usefulness separately from LLM scores. Avoid public productivity rankings,
compulsory streaks and completion inferred from time spent online.

Start with a bounded pilot; validate whether the spatial version adds value over
the native non-spatial entry. Agree success thresholds before pilot analysis,
using a baseline rather than invented percentages in this document.

**Alternative considered — not selected:** optimize primarily for time in World or number of model turns.
Those can reward distraction and cost while saying little about user benefit.

**Applies to:** release evaluation, not the first implementation plan.

## Next work under the accepted decisions

Proceed with the detailed focus-lounge framing using D01, D02, D07, D09, D10 and
D11. Define its lifecycle, source-backed integration plan, effective limit
proposals, resource-retention map and FOC acceptance evidence. The focus chat
must not reopen these product decisions as prerequisites to analysis.

The training chats consume D03–D07; the camp chat consumes D08. All chats inherit
the common spending, permissions, availability and validation contracts.

Remaining work is design and qualification, not an unapproved D01–D11 choice.
Propose routine details from current evidence. Escalate only a newly discovered
contradiction, a material extension of scope or a genuinely new owner decision;
explain why and keep independent analysis moving. Record any later revision with
its date and affected briefs so no chat becomes a hidden source of truth.
