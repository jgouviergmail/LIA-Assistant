# Continuity, qualification and delivery ledger

[Master plan](README.md) · [Contract evidence](contracts.md) · [Decisions](decisions.md)

## Snapshot and limits of this assessment

- Date: 2026-10-29; repository: `D:\Developpement\LIA`.
- Branch: `main`; starting HEAD: `b32961fc98b7dbed89b372a8a92c2b3e889a963d`.
- The initial inventory contained 578 tracked paths with changes, six unstaged
  entries and five untracked entries. Some staged paths were also unstaged.
  This is provenance of a local snapshot, not a codebase size or release count.
- `CLAUDE.md`, World, Live, accounting, registers and Workboard include local
  changes. A HEAD link alone would not describe the inspected state.
- Evidence: current source, root instructions, relevant ADRs and existing test
  locations. No production, deployed model configuration or provider account was
  queried; no paid model call, database migration or runtime experiment was run.
- [CLAUDE.md](../../../../CLAUDE.md) is authoritative;
  [AGENTS.md](../../../../AGENTS.md) is generated and was not edited.

The initial documentation preview passed. The final verification record below
is the evidence for this documentation delivery, not qualification of any future
feature.

## One source of continuity

Use this dossier as the entry point for the four chats. Existing code and accepted
ADRs retain authority over current behavior; the dossier describes desired changes
and the decisions accepted on 2026-11-03. Detailed design proposals and runtime
qualification remain distinct from that acceptance. If sources disagree, record
the discrepancy and
refresh the fact rather than silently changing an accepted contract.

Keep stable identifiers:

- F01–F13: current contract evidence in [contracts](contracts.md).
- D01–D11: owner choices in [decisions](decisions.md).
- FOC, THE, LNG and CMP: feature acceptance criteria in the corresponding briefs.
- G0–G5: delivery gates in the [master plan](README.md).

Do not use another chat's implicit memory as authorization. Record an accepted
choice with date, exact scope and affected documents. If a cross-cutting choice
changes, update its shared record and affected briefs before treating it as the
new implementation target. Create or amend an ADR in a later implementation
phase only when the actual architecture decision is accepted; discover the next
number then.

## Start-of-chat protocol

1. Read current `CLAUDE.md`, applicable nested instructions and relevant skills.
   Work inline unless the owner changes that instruction.
2. Inventory branch/HEAD, index and working-tree changes. Preserve other work;
   do not reset, stage or overwrite it as preparation.
3. Read this dossier and the feature brief. D01–D11 were accepted on 2026-11-03:
   apply them without asking for repeat approval. Distinguish this acceptance from
   any newly proposed details or later explicitly recorded revisions.
4. Re-read the code for affected F contracts, especially anything changed since
   this snapshot. Resolve code/ADR/document differences visibly.
5. Produce a bounded design and implementation plan mapping changed components
   to acceptance IDs, migration/lifecycle changes, test oracles and open blockers.
   Avoid promising unverified vendor/device behavior.
6. Implement only when the owner authorizes business implementation. Authorization
   to analyze or edit these documents does not include commit, push or deployment.

The [four launch prompts](README.md#mandate-and-reading-order) request detailed
analysis and planning first. This remains the owner's authorized scope after
accepting D01–D11 on 2026-11-03. Do not interpret acceptance as permission to
write business code, commit, push or deploy.

## End-of-chat handoff

Update the affected documents and the table below with:

- Scope actually achieved and what remains proposed.
- Accepted decisions, implementation revision/reference and dirty-tree caveats.
- Shared interfaces actually implemented, their owner and compatibility rules.
- Tests run, exact command/exit outcome, environment and evidence artifact.
- Failed or unavailable checks, open assumptions, remaining provider/device gaps.
- Migrations/configuration/operator choices still needed, without exposing secrets.
- The next chat's dependency and any contract it must not recreate.

If no implementation was authorized, mark it “design only.” Never promote a gate
to passed merely because the plan is complete.

| Workstream | Current status | Consumes | Must leave for the next consumer |
|---|---|---|---|
| Shared framing | D01–D11 accepted on 2026-11-03; detailed focus framing is next | Native contracts with a source refresh per feature | Accepted choices, detailed design and evidence boundaries |
| Focus | Not implemented by this dossier | G0, native World and accounting | Proven session/recovery conventions and optional ticket link |
| Theatre | Not implemented by this dossier | G0; focus conventions where useful | Isolated training lifecycle, Live matrix, feedback and attempt fixtures |
| Language | Not implemented by this dossier | Qualified shared training contracts | Pedagogical extension, supported language evidence, saved-progress lifecycle |
| Base camps | Not implemented by this dossier | Workboard; optional focus integration | Durable outcomes/references, permissions and real-work evidence |

## Cross-cutting acceptance matrix

Apply these checks to every relevant feature rather than assuming another
workstream proved a new code path.

| Contract | Required test oracle |
|---|---|
| Cost ownership | Join known provider usage to the authenticated account, native run and decision; no duplicate row on command replay |
| Personal key | Live vendor expenditure is separate from platform calls and absent from platform-quota sums |
| Quotas | Account blocked, instance blocked, per-account flag off with instance blocked, unknown owner, and each native error policy |
| Rates and concurrency | Duplicate client command, two tabs, two accounts, active Live conflict, session expiry and stale revision |
| Retry safety | Failure before send versus after possible send; partial stream; lost final response; reconnect only re-reads result |
| Registers | Actual decision/outcome, effects only for real native actions, direct-read consultations declared; no fictional success |
| HITL | Direct endpoint and tool entry cannot bypass required approval; edited/stale approval revalidated by native authority |
| Privacy | Guessed IDs, shared snapshots, public nameplates, observer peers, account changes and revoked capabilities expose no private content |
| Training isolation | Actor, debrief, transcript, standby, end, timeout and late callback cannot write ordinary history or invoke personal-learning extractors |
| Persistence | Explicit source of truth, export, selective delete, account purge, chat reset, expiry and late-write fencing |
| Model configuration | Effective slot/model/capability and prompt versions; missing or unsupported configuration yields an honest unavailable state |
| Recovery | Browser reload, worker restart and unavailable Redis recover only confirmed state; no private fallback process-local authority |
| Accessibility | Keyboard, touch, narrow screens, reduced motion, focus restoration and always-reachable stop |
| Resource bounds | No model/render-per-frame coupling; bounded context, work, fanout and retained data; no shared AsyncSession in parallel work |

## Qualification contract

Implementation chats must use the commands actually defined in
[Taskfile.yml](../../../../Taskfile.yml) at that time. Select the relevant unit,
real PostgreSQL/Redis integration and browser journeys, then run required
repository gates before claiming code ready. Never weaken a gate to fit the
feature.

Evidence levels must be named separately:

1. Static source contract and architecture check.
2. Automated unit/contract tests.
3. Real database/Redis races and lifecycle tests.
4. Native browser/device interaction.
5. Actual provider/transport behavior and linguistic/product evaluation.
6. Deployment/production verification, only when separately requested.

A mocked Live smoke test is not evidence for a real microphone, mobile audio
route or vendor transcript retention. Browser emulation is not a physical-device
performance claim. A passing docs preview only qualifies documentation structure.

Agree runtime latency/resource and product-success thresholds before the pilot.
Measure initial state, compare the same scenario afterward, and publish both the
effective configuration and the qualification limits. Do not hard-code a model
price, repository coverage floor or vendor feature in this dossier.

## Documentation delivery verification

**Baseline:** `task lint:docs:preview` passed on the inherited working tree.
Its historical stale-path inventory was informational; living links and stale
paths had no findings.

**Final checks:** `task lint:docs:preview` passed after dossier creation and index
linking: links/path audit, quoted source facts, living maps and language ratchet.
The separate read-only `agents_mirror.py` and `findings_register.py` checks also
passed. The latter still reports existing open findings; passing its consistency
check does not resolve them. `git diff --check -- docs/INDEX.md` passed. All local
Markdown link targets in the twelve-document dossier were separately resolved.

**Preservation:** HEAD, branch and the Git index byte hash remained unchanged at
comparison. Every initially untracked path was still present. Our writes are the
twelve new dossier documents and one added link in `docs/INDEX.md`; no business
source was edited, staged, committed, pushed or deployed by this work.

Seven other initially dirty files changed concurrently during the assessment:
the English/Spanish/Italian locale JSON files and the English/French/Spanish/Italian
`story` guides under `apps/web/`. They were not written or reverted by this task.
The other initially dirty tracked-file hashes matched the starting snapshot,
apart from the intentional index-document addition. This is a scoped preservation
check, not a claim that the whole working tree was frozen.

No business feature is marked qualified by this document.

## Acceptance update — 2026-11-03

The owner accepted all D01–D11 recommendations and requested a complete prompt
for detailed focus framing, inline and without business code. The master plan,
decisions, four briefs, contract-evidence date caveat and four launch prompts now
reflect that acceptance. The documentation index points to the accepted status.

This update started on `main` at
`a221721d6f95c6b035dd7f1d27f83009d789bb05`. The tracked working tree was clean;
an existing untracked `LIA/` entry was left untouched. The 2026-10-29
preservation and qualification record above remains historical evidence, not
a claim about this newer checkout.

**Qualification:** `task lint:docs:preview` passed, as did `git diff --check`;
all local dossier link targets resolved. Historical/roadmap path findings remain
informational and are not reported as repaired. The diff contains only the twelve
dossier documents and their documentation-index entry. HEAD and the Git index
byte hash match the starting snapshot; the pre-existing untracked entry remains.
No runtime/source re-audit or feature implementation is claimed.
