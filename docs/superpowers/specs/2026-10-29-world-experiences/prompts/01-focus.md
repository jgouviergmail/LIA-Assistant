# Launch prompt — Focus lounge

[Master plan](../README.md) · [Feature brief](../01-focus.md) ·
[Accepted decisions](../decisions.md) · [Handoff protocol](../handoff.md)

**Updated: 2026-11-03.** D01–D11 are accepted. Copy the complete prompt below
into a separate chat attached to the LIA repository. This requests detailed
analysis and documentation only, strictly inline.

```text
Start detailed framing of the accompanied focus lounge in LIA World, in the
repository D:\Developpement\LIA.

Work strictly inline, without subagents or delegation to another chat. This
request authorizes read-only analysis and repository documentation changes only.
Do not write business code, migrations, tests or runtime configuration. Do not
run paid model calls, change runtime data, stage, commit, push or deploy.
Do not create a new chat or worktree. Preserve all existing changes and files.

Communicate with me in French. Write repository documentation in English under
the current CLAUDE.md conventions. Use relevant skills within the inline constraint.

1. Establish the current baseline

Read current CLAUDE.md, applicable nested instructions, Taskfile.yml and relevant
architecture decisions. Inventory HEAD, the Git index and working-tree changes.

Read these files from the existing reference dossier:
- D:\Developpement\LIA\docs\superpowers\specs\2026-10-29-world-experiences\README.md
- D:\Developpement\LIA\docs\superpowers\specs\2026-10-29-world-experiences\contracts.md
- D:\Developpement\LIA\docs\superpowers\specs\2026-10-29-world-experiences\decisions.md
- D:\Developpement\LIA\docs\superpowers\specs\2026-10-29-world-experiences\01-focus.md
- D:\Developpement\LIA\docs\superpowers\specs\2026-10-29-world-experiences\handoff.md

I accepted D01–D11 on 2026-11-03. Apply them without asking me to approve them
again. The source audit dates from 2026-10-29: re-read affected code and report
drift; do not present the old snapshot as current production evidence.

2. Apply the accepted focus scope

- A useful deterministic focus interval that works without LLM access.
- Solo work and voluntary co-presence under existing peer/consent rules.
- A private intention, an optional native Workboard ticket reference, a shared
  rhythm when applicable, and explicit start/stop/completion controls.
- Optional private coaching, explicitly requested and attributed to its requester.
  No paid group facilitator, automatic monitoring or periodic background LLM work.
- A private recap and next step; saving and real ticket changes remain explicit.
  An elapsed interval never means a ticket is done.
- Independent native capability controls, accessible keyboard/touch entry and
  preserved acknowledged state when leaving World.
- Native account/instance quotas plus bounded operations, without a new central
  monetary reservation system or a promise of an exact monetary cap.
- The accepted 24-hour default applies to transient transcript/resume content
  where relevant. Map its resources and clock anchor; do not impose that TTL on
  native accounting receipts or explicitly saved outcomes. No raw audio by default.
- No new peer-voice requirement, game engine, task system or billing subsystem.

D01, D02, D07, D09, D10 and D11 apply directly. Preserve future training isolation
and project authority without implementing theatre, language or base camps here.

3. Define the product and interaction design

Describe the complete solo and shared journeys: entry, private intention,
duration selection, joining an interval, active work, optional help, interruption,
end, recap and return to the selected ticket.

Make co-presence useful without disclosing the person's work. Specify shared
deadline versus individual participation, invitations/admission, late arrivals,
host departure, peer blocking, intentional stop, and whether solo pause is useful.
Keep participant consent separate from World presence.

Specify mobile, keyboard, reduced-motion, audio-priority and identity-change
behavior. Distinguish interval ended, user-reported progress and actual ticket
completion. Propose content-free outcome measures and pilot criteria rather than
time-in-World or token-volume targets.

4. Produce a source-backed technical design

For each concern, identify current files/symbols, reusable components, necessary
adaptations, actual gaps and the evidence needed:
- Tokens, costs, platform versus personal keys, payer identity, run/attempt IDs.
- Account and instance quotas, native failure semantics, rate limits, concurrency,
  duration/output bounds, idempotency and uncertain paid outcomes.
- Decision, effect and consultation registers; real authorship and native HITL.
- Ownership, permissions, peer consent, private projections and revocation.
- Memory/learning boundaries, explicit context selection and saved feature data.
- Persistence authority, retention, export/delete, account purge and chat reset.
- Server time/deadlines, revisions/leases, tabs, reconnect, crashes, late responses,
  capability loss and unavailable Redis/database.
- Native model slots, prompts, configuration and capability publication.
- Existing domain boundaries, import directions, async resource ownership and
  integration with World panels, Workboard and audio lifecycle.

Separate activity entry, individual interval and any shared rhythm. Propose
minimal typed data/API/event/state contracts as documentation only, with one
authority per fact. Reuse justified native primitives; do not build a universal
activity framework. Identify what theatre can later reuse without imposing a
focus state machine on it.

Propose routine design details from evidence. Numerical limits not already
approved must be labelled proposals, with their measurement/validation plan.
Ask only about genuinely new material choices or contradictions; explain why and
continue independent analysis. Never silently revise an accepted D decision.

5. Deliver reviewable documents and a handoff

Update the focus brief and add the detailed design and implementation plan using
repository conventions. Link them from the dossier and update handoff.md.
Keep shared fact corrections separate from accepted product decisions.

Include:
- User journeys and a precise first-release scope.
- Reuse/adaptation matrix with source links.
- State transitions, data/permission contracts and failure/recovery behavior.
- Retention, accounting and register flows, including uncertainty.
- Ordered implementation batches with dependencies and estimated complexity,
  not unsupported delivery dates.
- A validation matrix mapping every FOC-01–FOC-10 criterion to observable
  evidence; identify real PostgreSQL/Redis, browser/device and provider checks.
  Plan those tests; do not implement or run feature/runtime tests in this phase.
- Remaining detailed proposals and recommendations, plus an accurate next-step
  handoff for future implementation and shared foundations.

Run appropriate read-only documentation checks, verify links and inspect the
scoped diff. Confirm preservation of the starting index and unrelated work.
End with document links, key design conclusions and any genuinely new arbitration.
Stop at this documented, reviewable framing; do not begin business implementation.
```
