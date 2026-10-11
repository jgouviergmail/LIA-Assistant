# ADR-337 — Checkpointed ReAct read segments and turn-local reuse

**Status:** Accepted — implemented and qualified locally; deployment is not certified.
**Date:** 2026-10-07
**Deciders:** The owner authorized semantic execution improvements;
Codex recorded the implementation choices and their measured limits.
**Scope:** ReAct tool execution, graph state, read concurrency, result reuse and mutation freshness.

**Amends:** [ADR-070](ADR-070-ReAct-Execution-Mode.md),
[ADR-092](ADR-092-Replay-Safe-HITL-Interrupts.md),
[ADR-248](ADR-248-React-Memory-Parity-And-Progress-Earned-Budget.md) and
[ADR-256](ADR-256-React-Budget-Conservation-And-Declared-Tool-Safety.md).
**Related:** [ADR-022](ADR-022-LangGraph-State-Checkpointing.md) and
[ADR-308](ADR-308-ReAct-Cross-Turn-Prompt-Cache.md).

## Context and problem statement

LangGraph re-executes a node containing an interrupt when it resumes. A node
that already performed independent reads before reaching a confirmation can
repeat those reads, spend quota again and observe changed data. A process-local
set of completed calls cannot protect a resume in a new graph instance.

Sequential execution also pays the summed latency of independent reads, and
identical reads can repeat within a turn. Read-only classification alone does
not establish that a tool is independent, safely reusable or non-interruptible:
a delegation can perform hidden work, and a mutation attempt can change remote
data even if its reported outcome is a failure.

## Decision

1. **Commit completed read segments through graph state.** Eligible independent
   reads form bounded segments. Each completed segment returns its progress,
   correctly paired tool messages, canonical registry observations and execution
   accounting so the graph checkpoints them before advancing to a potentially
   interrupting call. Resume continues from persisted progress, including in a
   new graph instance. This extends the replay-safe boundary of ADR-092 to the
   reads preceding a ReAct interruption.
2. **Concurrency requires explicit eligibility.** Only declared independent,
   non-interrupting reads run concurrently, under the implementation's bounded
   limit. Unknown, mutating, interruptible and delegated calls retain sequential
   execution. Declaration is checked on the available request manifest; it is
   not inferred from a convenient tool-name prefix.
3. **Reuse is a fresh exact observation within one turn.** Reuse requires an
   explicit positive manifest TTL and an obtained, successful, nonempty,
   nonpartial result. The exact normalized arguments, public and semantic schema,
   MCP owner identity, account/thread and runtime timezone, language and browser
   context contribute to the signature. Turn-start reset, expiration, explicit
   refresh and schema/context changes prevent reuse. A reused observation keeps
   its original provenance and creates a ToolMessage paired with the new call.
4. **The bounded read cache is checkpoint state.** JSON-compatible result entries
   are limited by entry count and serialized bytes, with limits owned by
   [the implementation](../../apps/api/src/domains/agents/nodes/react_read_reuse.py).
   Persistence permits another worker to resume the same turn. This is not a
   shared MCP result cache, a cross-turn result cache or distributed coherence
   for process-local discovery/session caches. ADR-308's provider prompt cache
   remains a separate mechanism.
5. **Attempted writes invalidate at both boundaries.** Before a mutating or
   delegated invocation, invalidate reusable reads and prior semantic proof;
   invalidate again on completion, including failure. This also catches reads
   finishing while a write is in flight. The pipeline shares the proof rule in
   [ADR-335](ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md).
   Rejected arguments before invocation do not claim that a remote write ran.
6. **Budgets and message validity survive segmentation.** Check budgets between
   segments and preserve charged execution time through a resume. Every call
   abandoned by a budget exit receives its explicit closing ToolMessage, as
   required by ADR-248. Sandbox computation receives usable canonical JSON on
   stdin and retains its charged budget through checkpoint reconstruction.

## Considered options and trade-offs

| Option | Benefit | Reason for the decision |
|---|---|---|
| One sequential node with a process-local completed set | Minimal graph changes | Replays prior reads when the node or worker restarts |
| Run every apparent read concurrently | Maximum immediate parallelism | Read labels do not establish independence or interruption safety |
| Reuse all successful reads across turns | Larger apparent call savings | Breaks turn freshness, ownership and mutation assumptions |
| Checkpointed segments and opt-in exact reuse | Saves repeated work while preserving provenance and resume state | Selected; adds bounded checkpoint data and requires conservative declarations |

## Consequences

Independent reads can overlap and completed reads need not replay after HITL.
The cache deliberately misses uncertain, empty, failed or incomplete results.
Invalidation can force another read after even a failed write attempt. Checkpoint
storage grows by a bounded amount; the existing registry and effect ledger
remain authoritative for their own responsibilities.

A hard crash inside a segment that has not reached its checkpoint can still
replay its reads. This decision does not make remote writes exactly-once after
a hard crash and does not permit arbitrary concurrent use of shared database
sessions. Existing effect admission, interruption and provider resource ownership
rules still apply; a reusable observation is not global provider consistency.

## Validation and follow-up

[Checkpointed execution tests](../../apps/api/tests/unit/domains/agents/nodes/test_react_checkpointed_execution.py)
exercise compiled graph paths, reads before HITL, reconstruction in another graph,
concurrency caps, budget exits and mutation invalidation. The
[execution qualification](../technical/SEMANTIC_EVOLUTION_QUALIFICATION.md)
records actual call counts, registry outputs and one controlled latency fixture;
the fixture is not a production latency claim.

Add eligibility only after a tool's interruption, freshness and independence
contract is established. Production latency and quota savings require their own
measurement rather than extrapolation from this fixture.

## Implementation references

- [Segment execution](../../apps/api/src/domains/agents/nodes/react_execution.py)
- [Individual call execution](../../apps/api/src/domains/agents/nodes/react_call_execution.py)
- [Read reuse](../../apps/api/src/domains/agents/nodes/react_read_reuse.py)
- [Serializable execution contracts](../../apps/api/src/domains/agents/utils/react_execution_contracts.py)
- [Turn reset and budgets](../../apps/api/src/domains/agents/utils/react_budget.py)
