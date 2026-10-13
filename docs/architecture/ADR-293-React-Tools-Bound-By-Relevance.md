# ADR-293 — The ReAct loop binds tools by relevance; the planner keeps its catalogue

- **Status**: Accepted
- **Date**: 2026-09-17
- **Amends**: ADR-070 (the ReAct mode « gets all available tools »), ADR-248
  (the loop knows what the pipeline knows — now including the tools' relevance),
  ADR-256 (the domain-aware cap), ADR-184 (a bound the code enforces is the one
  it publishes)
- **Scope**: `services/tool_selector.py` (`embed_query`, `rank_tools`),
  `nodes/router_tool_scoring.py`, `services/react_tool_selector.py`,
  `nodes/react_nodes.py` (setup), `metrics_react.py`, dashboard 20,
  `scripts/react/measure_tool_selection.py`, `REACT_TOOL_SEMANTIC_TOP_K`,
  `CATALOGUE_DOMAIN_COVERAGE_TOP_N`

## Context

The two execution modes select tools in opposite ways. The **pipeline** narrows
hard: the router scores the detected domains' tools semantically (calibrated,
thresholded, at most eight) and the planner's catalogue keeps a few of them
plus a coverage of two per domain — measured on a dev instance, a median of
four tools and about 1 800 prompt tokens per plan, with no panic-mode retry,
no hallucinated tool and no rejected step over the sampled turns. The
**ReAct** loop did the opposite, by doctrine: every available tool, then a
cap. Three facts made that a defect rather than a choice.

1. **The cap cut in registration order.** On any account with more tools than
   `REACT_AGENT_MAX_TOOLS` — a full catalogue plus a few MCP servers is enough
   — every turn was capped, and the tools cut were the SAME ones on every
   turn, whatever the question: the families registered last (workboard,
   peers, phone, skills, sandbox, and the whole of the user's own MCP tools).
   The detected domains' tools survived first, which is right, and the rest
   fell by position, which is a blind spot. Nothing about the question decided
   it.
2. **The schemas were the prompt.** A native tool schema costs 331 tokens on
   average; eighty of them cost 26 155, which was 95 % of the first model
   call of a turn and travelled again on every iteration. The delivered-context
   histogram never saw it: it counts messages.
3. **Nothing ranked the loop's tools.** The router's semantic scores covered
   only the detected domains' tools, for the planner. The loop had no
   relevance signal at all, although the query embedding those scores come
   from had already been paid for.

Replayed on 58 real ReAct turns of a dev instance over a week: the loop
called sixteen distinct tools; in the raw semantic order of every available
tool, the tools it called ranked at a median of 4.5 and a p90 of 32, with a
tail beyond 60 on open questions where the router had under-detected the
domains and the loop explored the person's other records.

## Decision

1. **One embedding, two readers.** The router still embeds the English pivot
   once. The planner's domain scores are byte-for-byte what they were. From
   the same vector, `rank_tools` orders EVERY available manifest AND every
   per-request vector that has no manifest of its own — an iterative user MCP
   server exposes one task manifest while its individual tools, the ones the
   loop binds, carry vectors and no manifest (found by the cold review: ranked
   from manifests alone, those tools could never rank and fell to the family
   coverage whatever the question). The order travels in
   `tool_selection_result["global_ranking"]`, a key of a dict the state
   already carried. No calibration on this path: the softmax is monotonic, so
   the order is the same and the raw scores compare across turns.
   `router_tool_scoring.score_tools_for_turn` is the one seam; every reader
   treats `None` as « no scores », exactly as before. The planner's scores
   need detected domains; the global order needs only the question, so an
   actionable turn the router placed in no domain — where the loop used to
   bind everything — is ranked all the same.

2. **The loop binds by composition, and no tool name is written anywhere.**
   `ReactToolSelector.select(intelligence, ranking)` binds, in this order:
   the detected domains' tools (all of them); then every OTHER family's
   `CATALOGUE_DOMAIN_COVERAGE_TOP_N` best-ranked tools — the planner
   catalogue's own coverage constant, now shared, so a family the router did
   not name stays reachable through its most relevant doors; then the first
   `REACT_TOOL_SEMANTIC_TOP_K` of the ranking. The rest is dropped by
   relevance, counted and named at debug. The cap stays the safety net, as a
   stable sort on tiers (priority, coverage, rest). Without a ranking, or with
   K = 0, every available tool is bound in registration order — the previous
   behaviour to the byte — and the cap trims by the same tiers. An expanded
   iterative user MCP server keeps its delegation door (the `_task` tool)
   beside its coverage, on no seat of its own and ranked as the best tool
   behind it: it is the one affordance for what the individual tools cannot
   express (ADR-224's measurement), it costs one schema per server, and
   relevance must never drop it while its server is bound.

3. **The rule reasons about the tool, never about one account's usage.** A
   declared list of « core » tools was written and rejected: it encoded what
   one deployment's turns had needed, and a multi-user product cannot carry a
   week of one person's habits as a constant. Family coverage says the same
   thing structurally — the person's records are families, and a family is
   reachable or it is not — without naming any.

4. **The planner catalogue is unchanged.** Its exposure is domain
   under-detection (a question about a person that names the contact domain
   alone), and the global ranking does not fix it: replayed, adding the two or
   three best-ranked tools outside the detected domains recovered one case of
   twenty, because « read my mail » ranks low for such a question. The
   pipeline's answer to that exposure is the response node's own context
   (memory, knowledge spaces) and the ReAct mode itself, which exists to
   explore; a heavier planner catalogue would pay tokens on every plan for a
   gap it would not close.

5. **The prefix is measured.** `react_tools_bound` beside
   `react_tools_resolved`, and `react_bound_tool_tokens` — the schema tokens
   every call of the turn carries — with two panels on dashboard 20 and the
   count in the `react_setup_complete` log. `task react:selection:measure`
   replays an operator's own turns (query, router domains, tools called)
   against the policy: what would be bound, at what token cost, and whether
   every tool the loop called would still be offered — the harness of this
   ADR, holding no one's turns.

## Alternatives rejected

- **Raising the cap** — the first reflex; it removes the blind spot at the
  price of every schema on every call, and the ordering defect stays.
- **Semantic top-K alone** — loses the exploration: replayed, three turns of
  fifty-eight had called a tool the ranking placed beyond the slice.
- **The planner's calibrated scores for the loop** — domain-scoped, and a
  distribution peaked by a temperature of 0.1: a rank, not a score, is what
  the loop needs.
- **A declared core of reads** — see decision 3.

## Consequences

- New: `router_tool_scoring.py`, `scripts/react/measure_tool_selection.py`,
  the task `react:selection:measure`, two histograms and two panels,
  `REACT_TOOL_SEMANTIC_TOP_K` (40, in the four application `.env` files; the
  cap comment they carried named a default of 25 that had been 100 for
  months), `CATALOGUE_DOMAIN_COVERAGE_TOP_N` (2, read by both modes).
- `SemanticToolSelector` gains `embed_query`, `rank_tools` and a
  `query_embedding` parameter on `select_tools`; the router node delegates its
  scoring block; the setup node mounts its context blocks through
  `react_context.build_setup_blocks`.
- Measured on the same 58 turns with the final policy (K = 40): a median of
  68 tools bound instead of every available one (73 at most), 22 488 schema
  tokens at the median instead of 35 471; three turns had called a tool the
  policy would not have bound, and in every one of them the tool's family
  was bound through its best-ranked doors. Latency: the ranking adds cosines
  over the available manifests in memory, no network.
- The debug panel's tool section reads the planner's calibrated keys only:
  a `tool_selection_result` carrying the global order alone (a turn whose
  domains own no tool, or placed in no domain) used to raise inside the
  panel builder, and the exception caught one level up blanked the WHOLE
  panel of the turn (found by the cold review; pinned by
  `test_debug_metrics_tool_selection.py`). `task react:selection:measure`
  replays through `ReactToolSelector.select` itself, never a copy of the
  composition.
- Not done, and said: no change to the router's domain detection, which
  remains the pipeline's real exposure on open questions; no re-ranking
  between iterations (the set is fixed at setup, as the state stores names).

## Amendment 2026-09-20 — a binding unit is bound whole or not at all

Replayed on dev with `task react:selection:measure` on the two skill requests
of the day (« je veux jouer au tic-tac-toe », « montre moi où je suis »): three
turns of three had called a skill tool the policy would not have bound —
`run_skill_script` for the map, `read_skill_resource` for the game — while
`activate_skill_tool` was bound through its family's coverage seat. That is
the production motif on both skills the same day: the loop activates the
skill, cannot run its script, and answers in prose. The four skills tools are
ONE affordance (a skill is activated, its script run, its resources read, a
library imported); each alone is a dead end, which is the rule ADR-249 states
for a tool a planner sees and cannot run.

No tool name enters the selector. The manifests declare it —
`ToolManifest.binding_unit`, the four skills manifests carrying
`SKILLS_BINDING_UNIT` and a guard refusing a fifth without it — and the
composition reads it: a unit ranks as its best member (the delegation door's
own rule), takes ONE coverage seat of its family, rides the semantic tail
whole, and the cap drops it whole rather than cutting inside it (the members
are adjacent in every order, so the cut walks back to the unit's first). A
unit no member of which is reached is dropped whole. Replayed: 0 of the 3
turns with an unbound skill tool (was 3), 62 tools bound instead of 60,
+427 schema tokens. Without a ranking nothing changes — every tool is bound.

## Amendment 2026-10-12 — a binding unit binds through its domain

Read on production (v3.0.0) after the owner reported high token spend and
latency on « occasional » exchanges: the rhythm was correctly resolved and
applied — every turn of 72 hours took the relevance selection, and the three
turns of a « frequent » test fell back on the cap (383 resolved tools against
300) — yet the selection bound 141 to 179 tools, 55K to 62K tokens of schemas
on every model call, and the two rhythms produced the same set.

The last turn's bound set, read from the checkpoint: 156 tools for a question
about the agenda — 6 of the detected domain, about 58 of family coverage (two
per family over 29 families), 23 of nine expanded MCP servers (a door and two
seats each), and **71 through twelve binding units of the settings catalogue**
(`lia_meetings` 18, `lia_peers` 9, `lia_relations` 7, …). The register of
treatments held ONE settings call in 125 ReAct turns of seven days. Over those
seven days the bound set ran from 81 to 181 tools (median 100), the variance
being the units.

The amendment of 2026-09-20 made a unit ONE coverage seat and ONE rank of the
semantic tail whatever its size, measured on the four skills tools (+427
tokens). Commit 499c4cecc (ADR-335 to ADR-338) then declared forty units
holding 180 tools in one family, and the rule was never re-measured: on the
agenda question the family's two seats were two whole sections, and every
section whose best member ranked in the first forty landed whole on that one
rank — 71 tools through twelve units in all.

A first correction counted a seat by its size but kept the family's first
seat whole whatever its size; on the owner's dev turns the settings family's
best section (`lia_meetings`, 18 tools) still rode the coverage seat on every
turn and its other sections rode the tail — 37 to 41 settings tools of 115 to
129 bound on agenda and mail questions — and when the router named the
`setting` domain the priority tier bound the whole family: 180 settings tools,
243 bound, 73 644 tokens of schemas on a real production turn. The owner's
verdict: the settings tools were treated unlike every other family, and that
is abnormal.

**Decision.** A unit still lands whole or not at all, and **a unit never
rides the tail**. A family holding at most ONE unit keeps the rule of
2026-09-20 unchanged: `CATALOGUE_DOMAIN_COVERAGE_TOP_N` SEATS, its unit one of
them whatever its size — one affordance, one door: the skills, the case that
amendment measured (a first draft counted that family's seats in tools too,
and would have dropped the skills whenever a loose sibling outranked them;
reviewed 2026-10-12). A family of SEVERAL units is a catalogue of sections
whose coverage seats count TOOLS (`_fitting`), and it is reachable through its
DOMAIN: when the router does not name it, it takes no seat a unit would
overflow (a section that fits the count still does, like any family's tools);
when the router names it, its loose tools are all bound and its units by rank
under `REACT_TOOL_SEMANTIC_TOP_K` tools, the first whole — the question is
about the family, not about every section of it. The tail counts TOOLS as
well. Every walk STOPS at the first seat that does not fit, never binding a
lower-ranked seat in place of a higher-ranked one (ADR-286's doctrine for the
paging of a tool result). The new set is a SUBSET of the old one on every
turn. Without a ranking nothing changes. No tool name enters the rule: it reads
the manifests' units and the router's domains.

**The prompt follows the binding** (ADR-284): the `<ApplicationSettings>` rules
of the ReAct prompt — read the options, use `setting_choices` values, a draft is
pending — are rendered only when a tool of the settings family is bound
(`react_settings_prompt.txt`, `react_prompt._render_settings_block`, the
`<Computation>` contract applied to the catalogue). Before this amendment the
family's best section rode a coverage seat on every turn, so the block was
always backed by a tool; after it, left unconditional, it would have described
tools absent from most turns. The family is named by ONE constant
(`SETTING_AGENT_NAME`), read by the domain config and the prompt assembler.

Stated, so a bound set can be read back from the log: `react_tool_selector_relevance`
carries the tier counts (`priority_count`, `coverage_count`, `tail_count`) and the
units bound whole (`unit_count`, `unit_tool_count`); `react_tool_selector_complete`
carries `every_tool_requested` beside `every_tool` (the two differ on every capped
frequent turn); `react_setup_complete` carries `exchange_rhythm` — the rhythm a
turn ran with was in no log line. `REACT_AGENT_MAX_TOOLS` may reach 500 (owner
request, 2026-10-12).

**Measured** on three real rankings read from checkpoints and replayed
through `ReactToolSelector.select` on the native catalogue of a dev instance
(303 manifests), previous rule → this rule: the owner's dev agenda turn, 140
tools and 49 443 schema tokens (73 of the settings catalogue) → 67 and 26 346
(none); the production agenda turn, 136 and 46 835 (70) → 68 and 25 236 (2: a
two-tool section that fits the family's two seats); the production turn whose
domain was `setting`, 243 and 73 644 (all 180) → 103 and 36 706 (40: the seven
best-ranked sections). The detected domains' loose tools and every other
family's coverage are identical in every pair. The repository corpus
(`scripts/react/selection_corpus.json`: synthetic questions and the tools they
need, no one's turns, every domain one the router CAN name — `query` and
`context` are not routable; its settings questions carry the `setting` domain,
as the router is expected to name it) replays through
`task react:selection:measure`. Not measured: the model's own choices on real
turns under the new set — no corpus of real questions exists (the conversation
resets purge them), so the proof is by construction (the subset property, the
reachability of every family, the units never split) and on the corpus.

A settings request the router does not route to `setting` now binds no settings
section: the catalogue is treated like every other family (the owner's
verdict) and reached through its domain alone, as the planner catalogue already
reaches it in pipeline mode. **Whether the router names `setting` on real
phrasings is not measured.** Its description (commit 499c4cecc) names font
size, theme, language, timezone, personality and feature preferences — not the
forty sections (meetings, knowledge spaces, memories, reminders, devices,
channels, …) — and over the seven days before this amendment the router named
it on none of 117 ReAct turns (Loki, production) while one settings tool ran
(register); one older checkpoint carried the domain. To verify on dev with a
handful of settings questions (a replay of the query analyzer on the corpus's
settings questions is a few model calls) before relying on it; a description
that names the sections is the lever if it fails, measured, never assumed.

Left open, for the owner: the family coverage itself — two tools of every
family on every turn, about 60 tools on a 36-family account plus the expanded
MCP servers' doors and seats — is ADR-293's « every family reachable »
guarantee and the remaining mass of the bound set; narrowing it (one seat for
families outside the best-ranked ones, a token budget) changes what the model
sees and is a product decision, not an accounting fix. Observed on the same
turns and not addressed here: a recovery pass (ADR-310, widened by ADR-336 to
observed gaps) ended `still_unresolved` on four dev turns of four and on 14 of
21 production turns in seven days, two model calls each; and the initiative
node runs before the response node, five to eight seconds ahead of the first
token.
