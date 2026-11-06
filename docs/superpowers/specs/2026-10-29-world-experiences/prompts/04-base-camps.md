# Launch prompt — Base camps for real projects

[Master plan](../README.md) · [Feature brief](../04-base-camps.md) ·
[Shared decisions](../decisions.md) · [Handoff protocol](../handoff.md)

Copy the complete prompt below into a separate chat attached to the LIA repository.
It requests detailed analysis and planning. Business implementation requires
the owner's explicit authorization.

```text
Start detailed framing of base camps for real projects.
Read the feature brief at
docs/superpowers/specs/2026-10-29-world-experiences/04-base-camps.md
and any actually completed focus handoff. Theatre and language are optional
links, not mandatory implementation dependencies.

Inspect current Workboard visibility, ticket lifecycle, hierarchy, assignments,
native approvals, results and runner recovery. Design camp outcome/reference
data around those authorities; do not duplicate tasks, statuses, schedules,
executors or permissions. A peer assigned one ticket gains no project-wide ACL.

Apply accepted D08: the first release is an owner-private camp with native peer
ticket assignment; full shared-project membership is deferred. Verify source
permissions again when read or passed to a model. Focus or rehearsal completion
cannot prove completion of real work.

Apply accepted D01 and D07–D11. Map CMP acceptance criteria, including
two-account database tests, revoked references, late writes, chat-reset
independence and account deletion. Return a reviewable bounded plan and update
the dossier with decisions and the precise remaining work.

Work strictly inline, without subagents. Communicate with the owner in French;
write new repository documentation in English according to CLAUDE.md.

Read current CLAUDE.md, applicable nested instructions and relevant skills.
Inventory HEAD, index and all existing changes; preserve them. Re-read current
code and ADRs rather than treating the dossier snapshot as current production
evidence. This launch authorizes analysis and documentation only: no business
code, commit, push or deployment. Later explicit authorization may expand that
scope.

Start from these repository-root documents:
- docs/superpowers/specs/2026-10-29-world-experiences/README.md
- docs/superpowers/specs/2026-10-29-world-experiences/contracts.md
- docs/superpowers/specs/2026-10-29-world-experiences/decisions.md
- docs/superpowers/specs/2026-10-29-world-experiences/handoff.md

The owner accepted D01–D11 on 2026-11-03 in decisions.md. Apply those decisions;
do not request repeat approval merely because this is a new chat. Distinguish
accepted direction, new detailed proposals and verified current behavior.
Escalate only a new material contradiction or scope change, with a recommendation,
while continuing independent analysis. Acceptance does not authorize business code.

Systematically map account and instance quotas, platform versus personal-key
cost, token attribution, rate/concurrency limits, decisions/effects/consultations,
HITL, permissions, memory/learning, persistence/export/deletion, retry safety,
models/prompts/capabilities and repository architectural patterns. Follow the
native authorities; do not create parallel billing, task or approval systems.

Deliver a concrete feature design, a component reuse/change map, migration and
lifecycle implications, and an ordered implementation plan with test oracles tied
to acceptance IDs. Identify runtime/provider evidence still missing. Update the
shared dossier with accepted decisions and your handoff; do not mark a feature
implemented or qualified from a design alone.
```
