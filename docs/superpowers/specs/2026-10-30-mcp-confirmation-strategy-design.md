# MCP — the person's confirmation strategy, who drives a server, and what it will do

Date: 2026-10-30. Status: approved by the owner on 2026-10-30, corrected the same day after
an adversarial re-read (see *Corrections*). Nothing is implemented.

## Intent

Owner's words (2026-10-30):

- *« Je pense que le réglage global MCP_HITL_REQUIRED doit être expliqué et modifiable sur
  la page "Serveurs MCP". Ainsi l'utilisateur a la main sur sa stratégie. »*
- *« Pour chaque serveur MCP : permettre à l'utilisateur de définir et modifier la valeur :
  oui, non, hérite ; si paramétré en "Mode itératif (agent REACT)" ajouter le réglage
  REACT_MCP_EXPAND_ITERATIVE_ENABLED expliqué et modifiable. »*
- *« Une synthèse claire de comment le serveur MCP va réagir en pipeline et react selon la
  définition de ces paramétrages. »*
- *« Une granularité plus fine sur chaque outil du MCP afin que l'utilisateur ait vraiment
  la main à la plus petite granularité. »*
- On never asking for a tool its server declares destructive: *« oui si c'est le choix de
  l'utilisateur »*.
- On the operator imposing confirmation: *« oui c'est assumé, chacun est ensuite
  responsable de ses réglages. Donc on ne verrouille pas, mais on peut émettre une alerte
  pour l'utilisateur qui changerait la valeur. »*

Approved in the same conversation: the strategy is the ACCOUNT's, never the instance's;
who drives a server is ONE choice, not a switch with a sub-switch; the synthesis is
computed by the API; per-tool choices are the last lot of this design; the chat assistant
may only make LIA ask MORE; the iterative path is proven on real turns before any of it is
offered.

The person must be able to decide, see and predict when LIA asks before using an MCP tool —
for the account, a server and a tool — in Pipeline and in ReAct, without reading a line of
configuration.

## Where things stand (verified 2026-10-30)

- **Nobody can see or set a server's confirmation.** `user_mcp_servers.hitl_required`
  (`True`: ask before every call; `False`: follow the server's declarations; `None`:
  inherit) has no field in the form. The chat assistant's configuration operation refuses
  it (`MCP_FORM_API_ONLY_FIELDS`, `domains/user_mcp/personal_configuration.py`), and a
  library install or a peer share writes `None` (`domains/user_mcp/service.py`, the create
  path). Only the REST API can set it.
- **"Inherit" means the instance.** A personal server's `None` resolves to
  `MCP_HITL_REQUIRED` (`infrastructure/mcp/user_context.py`, `_register_prepared`) — the
  value every account inherits, and the one the administrator's servers are registered
  with at boot (`infrastructure/startup/integrations.py`).
- **What is asked follows the server's declarations.** `derive_mcp_mutation_policy`
  (`infrastructure/mcp/registration.py`): with the server's confirmation on, every tool is
  `confirm`, reads included. Otherwise a tool declared destructive, or declared "not
  read-only" with nothing said about destruction (the MCP specification defaults
  `destructiveHint` to true), is `confirm`. A tool declared "not read-only, not
  destructive" is `reversible`. A tool declared read-only, or about which nothing is
  declared, gets no policy.
- **Two readers decide to ask, from the tool's manifest.** The ReAct loop asks before the
  call when `requires_confirmation(manifest)` says so (`domains/agents/registry/confirmation_rule.py`,
  read by `domains/agents/services/react_tool_selector.py`); the effect gate refuses an
  unapproved `confirm` call and turns it into a card (`domains/agents/effects/gate.py`), or
  approves it when a routine pre-approved its server (`domains/agents/effects/preapproval.py`,
  filed under its own `approval_kind`).
- **A tool whose server declares nothing runs unasked and leaves no action row.** No
  policy means a pass-through for the effect gate.
- **Who drives an iterative server in ReAct is an instance flag.**
  `REACT_MCP_EXPAND_ITERATIVE_ENABLED` (read in `react_tool_selector.py`) hands the loop the
  server's individual tools; with it off, the loop sees one task tool run by a dedicated
  agent. In Pipeline an iterative server is always that task tool. `MCP_REACT_ENABLED` off
  removes dedicated agents from the instance, and an MCP App server keeps its dedicated
  agent in ReAct.
- **The form's switch misleads.** « Mode itératif (agent ReAct) » uses "ReAct" for the
  chat's execution mode AND for the dedicated agent's technique; its help text speaks of
  cost only.
- **One setting, two experiences, said nowhere.** With the server's confirmation on, a
  dedicated agent asks ONCE, before its task (`build_mcp_react_task_manifest`), while
  direct tools ask at EVERY call.
- **A shared copy carries its sender's shape.** A peer share installs the sender's
  `iterative_mode` (`domains/peers/capability_install.py`) and arrives disabled
  (`service.py`, the create path).
- **The iterative path was never proven on full turns.** The 2026-10-30 Docker proof ran on
  a standard server; the required run of a confirmed iterative task with confirmation on was
  not made (ledger of the 2026-10-29 confirmation programme, post-final entry).

## What the person gets

On the MCP servers page:

1. **The confirmation strategy of the account**, at the top, explained in a few lines.
   Three choices: always ask; follow the servers' declarations; the default (stating what
   it currently is). Never chosen, it follows the instance and says what that is.
2. **In each server's form, its confirmation.** Three choices: always ask; follow this
   server's declarations; like my strategy (stating what that currently gives).
3. **In each server's form, who drives the server.** Three choices: LIA uses its tools
   directly; a dedicated agent in Pipeline and the tools directly in ReAct; a dedicated
   agent everywhere. Only the choices that apply to this server on this instance are
   offered; the others are shown disabled, with the reason.
4. **On each saved server, what it will do** — and this replaces the bare list of its
   tools. Per mode (Pipeline, ReAct): who drives, and when and how LIA asks; tool by tool,
   whether it asks and why; one line on what happens when nobody is there (a routine, a
   ticket). It follows the form as it is edited, before saving.
5. **On each tool of that synthesis (last lot)**: by default (stating what that gives);
   always ask; never ask.
6. **An alert before any change that makes LIA ask less.** Whatever the level — account,
   server, shape, tool — the page lists what LIA will no longer ask about and says the
   person stays responsible for the setting; the change applies once they confirm. Nothing
   is locked.

In the chat, "always ask me before using this server" is carried out through the
assistant's existing configuration card; "stop asking me" is refused with the path to the
settings page.

The FAQ answers the two new questions (how to decide when LIA asks before an MCP tool; who
drives a server), and its existing MCP answers are brought up to date, in six languages.

### Non-goals

- The administrator's servers. Their tools are registered once at boot for every account;
  their confirmation stays the operator's configuration.
- An operator lock. The instance settings become defaults; nobody can force a
  confirmation on an account (owner decision).
- Changing the default for a tool whose server declares nothing (not asked, not recorded).
  The synthesis says it plainly, and the person's lever is "always ask" on that tool.
- The routine pre-approval per server (spec 2026-10-29, D9): a routine still confirms only
  what its form ticked.
- An administration screen for the instance settings: they stay environment settings.
- Which tools the planner selects. The catalogue's coverage cap can still leave a tool out
  of a plan (found 2026-10-30); the synthesis describes confirmations and shapes, never
  selection.
- Where a read approved under "always ask" is filed: today an approved `confirm` call is
  recorded as an action even when it only reads. Pre-existing, unchanged here.

### Anti-goals

- A synthesis that can disagree with a turn: written by hand, in the browser or in prose.
- A loosening the person did not make, or made without being told: by the assistant, by a
  copy received from someone else, by a server that changed its declarations.
- A choice about asking that changes what a tool IS: its category, the initiative's
  read-only requirement, the invalid-mutation safety net.
- A register that lies: an act done without asking is recorded as an act, under the
  approval that let it run — never as `reversible`, never absent.

## Design

**D1 — Four levels, one resolution.** A personal tool's confirmation is decided by the
first level that says something: the tool (*always* / *never*), its server (*always* /
*as declared*), the account (*always* / *as declared*), the instance (`MCP_HITL_REQUIRED`:
true is *always*, false is *as declared*). The resolution is ONE pure function, called where
the person's MCP manifests are built for a run (today `_register_prepared`), whatever the
run: a chat turn, a routine, a ticket, a voice session. The account's value is read there,
from the person's row. A change applies from the next run, on every worker.

**D2 — The account's strategy.** One nullable column on `users`, in a declarative mixin like
the turn preferences; NULL follows the instance — the exchange rhythm's shape (ADR-311). The
MCP servers list publishes the three values the page needs (the instance's, the account's,
the effective one), as the routine list publishes its caps
(`ScheduledActionListResponse.recurrence_limits`); the page never holds a copy. It is
written through the generic profile update (`PATCH /users/{id}`), like the exchange rhythm:
strict on write, forgiving on read.

**D3 — The server's confirmation, and copies.** The existing `hitl_required` enters the form
with the three choices of § 2. A library install or a peer share still writes `None`, never
copies the ReAct shape (D4) or a tool choice (D6), and keeps the sender's `iterative_mode`
as today. The copy arrives disabled, and while it is, its card shows the synthesis opened:
the person activates a server whose behaviour they were shown (ADR-327).

**D4 — Who drives a server: one choice.** It replaces the « Mode itératif » switch:

| Choice | `iterative_mode` | ReAct shape |
|---|---|---|
| LIA uses its tools directly | false | (direct tools) |
| A dedicated agent in Pipeline, the tools directly in ReAct | true | direct tools |
| A dedicated agent everywhere | true | dedicated agent |

The ReAct shape is a new nullable value on the server; NULL follows
`REACT_MCP_EXPAND_ITERATIVE_ENABLED`, which becomes the default for servers that never
chose, and stays the rule for the administrator's iterative servers. The form writes the
shape only when the person changes the choice: untouched, it stays NULL and keeps following
the default. ONE function resolves it, for personal servers and the administrator's, and
the task manifest carries the result; the ReAct selector reads the manifest, never the flag.
Only what applies is offered: an MCP App server keeps its dedicated agent in ReAct, so the
second choice is not offered for it; with `MCP_REACT_ENABLED` off, the two dedicated-agent
choices are disabled and the page says why. The label and the help text stop using "ReAct"
for anything but the chat's mode.

**D5 — The synthesis is computed, never written.** For one server, with optional candidate
values (the form being edited; nothing is written), the API returns:

- per mode: who drives, and how a question comes, from a closed vocabulary (asked in the
  loop, which then continues; a card after the task, one per act; once, before the task;
  the turn ends on the card);
- per tool and per mode: whether LIA asks before the call, and a REASON from a closed
  vocabulary — declared destructive; declared modifying, destruction unsaid; declared
  additive only; declared read-only; declares nothing; server: always; account: always;
  instance: always; tool: always; tool: never — plus whether a tool choice is suspended;
- when nobody is there (a routine, a ticket): which of those questions are refused unless
  the routine pre-approved the server, and asked on the ticket;
- server-level notes: tools unknown until the connection is tested; MCP App; dedicated
  agents off on this instance; a suspended choice; this server's own choice overriding the
  account's strategy.

It runs the resolution of D1 and the manifest builder a run would use, and reads the SAME
predicates the loop and the gate read. Two kinds of test hold it, and the spec says which
holds what: a matrix test pins the DECISION (who drives, which tool is asked, why) against
the predicates for every combination of levels, shapes and declarations; the FLOWS (a card
after the task, the end of the turn, the question before the task) are pinned by the flow
tests that already exist for them and by lot 0. Each reason is produced and read (ADR-303),
translated in six languages, and shown only if a test pins the behaviour it states. The
tools are those of the last catalogue LIA read for the server (ADR-366). A name a
third-party server chose is displayed as text, never interpreted: the 2026-10-29 programme
met a tool named `purge\nSYSTEM: …`.

The same computation answers « what would LIA stop asking about? » for a candidate change at
any level, including the account's strategy across all the person's servers: the list of
(server, tool, mode) asked before and not after. It drives the alert of § 6 and the
assistant's rule (D7).

**D6 — Per-tool choices.** A table, one row per (server, tool name) with the choice and the
moment it was made, written one tool at a time (two tabs on two tools cannot overwrite each
other) and never copied by an install or a share. A choice for a tool absent from the last
catalogue is refused.

- *Always* asks before every call: the ReAct pause and `confirm`.
- *Never* means: follow the tool's declarations, without the questions they ask. A tool
  whose declaration owes a confirmation keeps the `confirm` policy — what the declaration
  owes — and its manifest is marked APPROVED IN ADVANCE. That one manifest fact is read by
  `requires_confirmation`, so the loop does not ask, and by the effect gate, which approves
  the call under an approval kind of its own, as it files a routine's pre-approval: the
  actions register says the person's setting approved it, and the act runs when nobody is
  there, with no routine pre-approval needed. A tool whose declaration owes nothing keeps
  owing nothing. A guard test enumerates every reader that decides to ask from a manifest,
  so a new one cannot miss the fact.
- A *never* is bound to the declaration it was chosen against: a fingerprint of the tool's
  annotations AND input schema, computed by the server from the catalogue (the description
  is left out: it changes for cosmetic reasons). When the server changes that declaration,
  the choice is SUSPENDED: the tool falls back to the levels below, and the synthesis and
  the server card say so until the person chooses again.
- A choice for a tool the server no longer lists stays stored, inert and hidden. It applies
  again only to the same tool with the same declaration.

**D7 — The assistant asks more, never less.** For confirmation, the assistant may only
write *always* — the account's strategy (through the preferences operation), a server's
confirmation and a tool's choice (through its personal-server configuration operation,
already a card the person approves); any other value is refused with a sentence naming the
settings page. For the shape, the computation of D5 decides: a change that would make LIA
ask less is refused the same way. The check runs server-side at the write, against the
state the write replaces — never only when the card is proposed. The person's own settings
page is not bound by this rule. Reason: an instruction injected into content the assistant
reads must never switch a confirmation off — the owner's reasoning in ADR-314. Its read
surface (`infrastructure/mcp/personal_metadata_contract.py`) carries the new values so it
can describe them. The field-partition guard
(`tests/unit/domains/agents/application/test_personal_mcp_configuration_contract.py`) moves
`hitl_required` from "API only" to "tighten only" and adds the shape.

**D8 — Asking is not doing.** No choice of D1-D7 touches a tool's category, its initiative
eligibility or the invalid-mutation safety net: they keep reading the declaration and the
name heuristic.

**D9 — The instance settings become defaults.** `MCP_HITL_REQUIRED` serves the accounts that
never chose and the administrator's servers. `REACT_MCP_EXPAND_ITERATIVE_ENABLED` serves the
servers that never chose and the administrator's iterative servers. `MCP_REACT_ENABLED`
stays the instance's switch for dedicated agents. Nothing is locked (owner decision). The
env templates say so (the parity guard holds their wording).

**D10 — Prove the iterative path first (lot 0).** On Docker dev, on the proof account, with
the harness of the 2026-10-30 proof — `proof_full_turn.py`, run inside `lia-api-dev`: a fake
personal Notes server in the same process, only the pool's network edges replaced, the row,
probe, embeddings, adapters, manifests, gate, graph, HITL store and registers real. It lives
in a session scratchpad; the plan copies it into its git-ignored workspace and adds an
iterative mode. The server is set ITERATIVE: Pipeline (dedicated agent), ReAct with direct
tools, ReAct with the dedicated agent (the instance flag switched inside the harness's
process, since the per-server shape does not exist yet); the server's confirmation off (a
declared destructive tool) and on; including a confirmed task with confirmation on; and
what a delegated sub-agent does with a personal tool that must ask. Expected spend about
0.2 USD, cap 0.5 USD, read from `token_usage_logs` after each step; past the cap, stop and
ask. What it establishes is what the synthesis may state; a defect it finds is fixed
RED→GREEN, or reported, before anything is offered.

## Hypotheses to prove — each has its test

| | Hypothesis | Proof |
|---|---|---|
| H1 | Pipeline, dedicated agent, confirmation off: a declared-destructive call is presented after the task, as for a standard server | lot 0 |
| H2 | ReAct, direct tools: the call is asked in the loop, which continues | lot 0 |
| H3 | ReAct, dedicated agent: the turn ends on the card, and what was to follow the act is not done | lot 0 |
| H4 | Confirmation on, dedicated agent: one question before the task — and whether its calls are asked again | lot 0 (decides what D5 states) |
| H5 | A confirmed task with confirmation on resumes and runs | lot 0 |
| H6 | A changed strategy or choice applies from the next run on every worker | integration test |
| H7 | A suspended *never* falls back and is said | unit and integration tests |
| H8 | A delegated sub-agent calling a personal tool that must ask: what happens | lot 0 (decides what D5 states) |

## Lots

0. The real proof of the iterative path (D10). No code, unless it finds a defect.
1. The resolution: the account column and its mixin, the per-server ReAct shape, the pure
   resolution (D1), the shape resolution carried by the task manifest (D4), the instance
   settings as defaults (D9), the list's published values (D2); migrations.
2. The synthesis engine, its « what would LIA stop asking about » answer and their tests
   (D5).
3. The page: the strategy, the form's two choices, the synthesis and its live preview, the
   loosening alert, the opened synthesis of a received copy; six languages; a hermetic
   browser journey.
4. Per-tool choices: the table and its migration, approval in advance read by the loop and
   the gate, the register's approval kind, suspension, the page's per-tool choices (D6).
5. The assistant: always-only at every level, the shape judged by D5, its read surface (D7).
6. Documentation: a new ADR (the person's confirmation strategy and the computed
   synthesis) and an ADR-263 amendment (a declaration may be loosened by the PERSON's
   explicit choice for one tool, bound to that declaration); `docs/technical/MCP_INTEGRATION.md`,
   `docs/guides/GUIDE_MCP_INTEGRATION.md`; the FAQ (`mcp_servers` q6 and q11 updated, two new
   questions; `skills` q15; `scheduled_actions` q14); the living maps in six languages; the
   env templates and the four demonstrator files; one line in `CLAUDE.md`.
7. Gates, an exhaustive cold review, and a closing proof on the proof account.

Each lot ends green on its gates, with a cold adversarial review. Nothing is committed
(owner directive).

## Constraints

- Every visible string in six languages, the FAQ included; no fixed language in Python
  (ADR-323).
- A value the page shows that the code enforces comes from the API (ADR-184).
- Migrations with a downgrade, one head, the replay check.
- No new import cycle, no function at complexity 15 or more, the file-size ratchet: the
  modules near their cap (`user_context.py`, `registration.py`, `user_mcp/service.py`,
  `users/models.py`, `effects/runtime.py`) receive calls, not logic.
- Logs carry identifiers and counts; a server-chosen name is not logged above DEBUG
  (ADR-317).
- The reasons and the approval kind are produced and read; the table from a reason to its
  wording has a completeness check (ADR-085).

## Risks

- **The synthesis drifts from the turn.** It runs the turn's own resolution and builder;
  the matrix test pins the decision, flow tests and lot 0 the flows.
- **A reader decides to ask without the approval in advance.** One manifest fact, a guard
  enumerating the readers (D6) — the defect class the 2026-10-30 proof found.
- **Someone else loosens.** The assistant (D7), a received copy (D3), a server (D6,
  suspension) each have a test.
- **A cache keeps the old rule.** H6.
- **"Never ask" on a destructive tool surprises.** The alert lists it before it applies, and
  the act stays in the actions register under the person's approval in advance.
- **A tool that declares nothing stays unasked and unrecorded by default.** Pre-existing;
  the synthesis says it, and "always ask" covers it.

## My calls (the owner may override)

- The wording of the labels (final text in six languages).
- *Never* is bound to the tool's annotations and input schema, and suspended when they
  change.
- The person's approval in advance is an approval kind of its own in the register; the
  policy stays what the declaration owes.
- A choice for a tool that disappeared stays inert and hidden.
- The alert is shown for every change that makes LIA ask less, at every level, computed by
  the API; nothing is sent after the fact.
- The synthesis states only what a test pins, and adds one line for when nobody is there.
- The creation form, before the server exists, shows the shape only; the per-tool lines
  appear once the server is saved and connected.
- Lot 0: about 0.2 USD, cap 0.5 USD.

## Left to the plan

The names of the columns, the routes and the reason identifiers; the layout of the page;
how the matrix test enumerates its combinations.

## Review focus (for the plan)

1. A server whose catalogue is empty or being revalidated: the synthesis says "unknown",
   never "asks nothing".
2. A tool renamed by its server between two runs: its choice must not follow the new name.
3. An MCP App server switched between shapes: the page must not offer what the selector
   will not do.
4. The instance flags changed by the operator while accounts have chosen: every "currently"
   on the page must follow.
5. A loosening reached through two steps that each look harmless (the account first, then a
   server back to "like my strategy"): each step's alert must list what it alone removes.

## Corrections (2026-10-30, adversarial re-read)

The first version kept `confirm` on a *never* tool and let the gate alone approve it: the
ReAct loop decides to ask before the call from the manifest (`react_tool_selector.py`), so
it would still have asked. It also stored the per-tool choices in one JSON value per server
(two tabs lose a choice), bound a *never* to the annotations alone (a server could keep
them and change the inputs), claimed a matrix test could pin the flows, left the copies'
shape in contradiction with its own anti-goals, said nothing of the delegated sub-agents,
and kept two lists of tools on one card. Each is corrected above. The owner then decided
that nothing is locked and that a loosening change is announced to the person (§ 6).

## Owner decision (2026-10-31, after reading the page)

The owner read the synthesis of lots 2-4 and asked five questions; the answers, measured,
changed the design in three places.

- **A dedicated agent is asked once before each task it is given, whenever one of its
  tools would ask** — in Pipeline and in ReAct, with « always ask » and with « follow its
  declarations ». That answer covers the agent's calls for the task, and the task runs to
  completion. The owner's rule: *whatever the mode and the level, a task runs to completion
  once the person validated an action that needed it.* Before, a dedicated agent was asked
  before its task only under « always »; under « follow its declarations » its first
  sensitive call became a card, the turn ended, and after the person's yes only that act ran
  (lot 0, H1 and H3) — the rest of the task was lost. ONE predicate decides it, over the
  manifests of the agent's own tools, for the person's servers and the administrator's, and
  the synthesis reads the same predicate. A tool on « never ask » does not make the task
  ask; a tool on « always ask » does.
- **A question before the task counts as asked.** The synthesis said « Pipeline : does not
  ask » for a tool whose call the question before the task covers, and the « what would LIA
  stop asking about » computation counted that coverage as a loss. Both now read the
  question before the task as the person's oversight of the task's calls: the tool's row
  says it is asked before the task, and moving a server to a dedicated agent loses nothing.
  The flow « the turn ends on the card » disappears with the defect it described.
- **Correction of lot 0's reading of H4.** ReAct with a dedicated agent under « always »
  asked once per TASK, not once per call: the loop gave the agent four successive tasks
  (review, delete, archive, list again), each asked once, each covering its own calls. The
  synthesis said otherwise (« asked in the loop, then continues » under a task question);
  it now says what both modes do: LIA asks before each task it gives the agent.
- **Per-tool choices are also offered in the server's configuration form**, saved with the
  form (one alert for everything that would make LIA ask less), besides « What it will do »;
  a « never ask » choice is drawn in the warning colour, its words kept.
- « Not asked » means: LIA runs the tool without asking, as if the person had said yes; the
  act is still recorded in the actions register.
