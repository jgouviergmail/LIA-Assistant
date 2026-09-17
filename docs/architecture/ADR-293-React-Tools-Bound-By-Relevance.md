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
