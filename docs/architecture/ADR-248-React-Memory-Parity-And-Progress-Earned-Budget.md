# ADR-248 — ReAct: memory parity, progress-earned budget, and no promise served as an answer

- **Status**: Accepted
- **Date**: 2026-08-28
- **Supersedes in part**: ADR-238 (adaptive ReAct budget — its domain-span
  allowance becomes the INITIAL budget, no longer the final one)
- **Related**: ADR-070 (dual execution modes), ADR-079 (ambient portrait),
  ADR-182/184 (never invent, publish what you enforce), ADR-236 (procedural
  memories), ADR-247 (answer resilience)

## Context

One production turn exposed three independent defects at once. A user asked, in
ReAct mode, for the transfer times of a return flight. LIA answered:

> « Je plonge dans tes emails pour retrouver les détails de ton vol […] Donne-moi
> une minute, je te sors ça. »

and the turn ended there. No numbers, no continuation — the user had to ask
again. Worse, they had a standing instruction in long-term memory forbidding
exactly that behaviour, and it had no effect.

The logs (Loki, run 11:29:01→11:29:33) contradict the obvious reading: **LIA was
not refusing to act.** Six iterations ran, each executing a tool. The loop was
cut mid-flight by its iteration budget.

Three causes, each verified in code:

1. **A promise served as an answer.** `react_finalize_node` took the content of
   the last `AIMessage` as the final answer. On a budget exit that message still
   carries UNEXECUTED `tool_calls`; its text is the model narrating what it is
   about to do. The pending calls were dropped in silence and nothing told the
   user the search had been cut.
2. **A budget that measures the wrong thing.** ADR-238 scales the allowance with
   the query's DOMAIN SPAN. Span says how *wide* a question is; it says nothing
   about how *deep* the answer is buried. A single-domain email investigation
   therefore got the minimum — six iterations — and spent all six productively.
3. **No memory in the loop at all.** `injected_memories` was declared in
   `MessagesState`, read by the ReAct setup, and **written by nobody** anywhere
   in the repository. The loop reasoned with zero memory. The psychological
   profile reached only the response node, where the ReAct answer is already
   *authoritative* — so a standing rule arriving there can reword a promise, but
   never turn it into an action.

## Decision

### 1. A message with pending tool calls is never an answer

`react_finalize_node` refuses to publish the content of an `AIMessage` that
still carries `tool_calls`, and publishes an empty `final_message` instead —
the path the draft handoff already uses, which makes the response node
synthesise from the tool results that DID come back.

The stop reason travels with it (`react_agent_result.truncation`) and is
rendered by a versioned directive (`react_truncation_directive`) telling the
answer to give what was found, say in one sentence that the search was
interrupted, offer to continue — and never to announce future work, because
**a turn ends when its answer is sent**. That directive is deliberately NOT
gated on `diagnostics_enabled`: telling the truth about our own run is answer
quality, not observability.

The stop condition itself becomes ONE predicate, `react_exit_reason`, read by
the router (to decide) and by the finalize node (to explain). Two copies would
let the loop stop for a reason the answer never mentions.

### 2. The budget is earned with results, not granted by shape

ADR-238's adaptive value becomes the **initial** allowance. Each time the loop
reaches its allowance having spent it PRODUCTIVELY, it is granted another block
(`react_iterations_progress_extension`, default 4). A loop that stops producing
stops being extended, and ends.

*Productive* means the context learned something: a tool returned a result that
is neither `success: false` nor empty. An attempted call is not productivity —
otherwise a loop could buy iterations with its own failures.

The hard bounds are unchanged: `react_agent_max_iterations` (ceiling) and the
compute-time budget. The repetition brake (`no_progress`) still short-circuits a
loop that repeats itself.

### 3. The loop knows what the pipeline knows

`react_setup_node` injects the user's psychological profile through
`build_psychological_profile` — **the same builder the pipeline uses**, the same
settings, the same triviality gate, the same `user_memory_enabled` preference.
Standing rules lead the context blocks, because they govern how everything after
them is used.

This is the treatment already applied to journal directives ("the ReAct
reasoning loop was blind to behavioural directives"); memory simply gets the
same. The dead `injected_memories` key is removed rather than left as a
plausible-looking hook.

The setup's context assembly moves to `nodes/react_context.py` — one builder per
block, each best-effort, each returning `None` when it has nothing to say.

## Consequences

- **Cost.** A ReAct turn now embeds the user message (shared get-or-compute
  cache, so the response node's later call reuses it) and adds the profile to
  the loop prompt. Deep investigations may run longer than six iterations. This
  is a deliberate trade: the product's objective is the best answer, and a
  truncated search that has to be asked again costs the user more than the
  tokens saved.
- **A cut-short run now costs one extra synthesis call** (empty final message →
  the response node synthesises). It buys an answer instead of a promise.
- **Extensions are observable**: `react_productive_iterations` is state, and the
  truncation reason is logged and rendered.
- **Defaults**: progress extension is ON. A self-hoster who wants the historical
  behaviour sets `REACT_PROGRESS_EXTENSION_ENABLED=false`.
- ADR-238 is not withdrawn: domain span remains the right way to size the
  *initial* budget — a three-domain question does start wider.
