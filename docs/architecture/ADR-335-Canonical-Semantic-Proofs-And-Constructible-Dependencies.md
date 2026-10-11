# ADR-335 — Canonical semantic proofs and constructible dependencies

**Status:** Accepted — implemented and qualified locally; deployment is not certified.
**Date:** 2026-10-07
**Deciders:** The owner authorized the semantic review and its improvements;
Codex recorded the implementation choices and their measured limits.
**Scope:** Ontology, field contracts, request catalogue, parameter guards and both execution modes.

**Amends:** [ADR-090](ADR-090-Semantic-Layer-Governance.md),
[ADR-120](ADR-120-Semantic-Evidence-Expansion-And-Param-Guard.md),
[ADR-121](ADR-121-Semantic-Annotation-Backfill.md),
[ADR-183](ADR-183-Catalogue-Closure.md) and
[ADR-233](ADR-233-ontology-simplification.md).

## Context and problem statement

Matching semantic type names makes a cross-domain path plausible but does not
establish its meaning or executability. A city named Nancy is not evidence for
the home address of a person named Nancy. A producer requiring its own output,
or two producers requiring each other's output, cannot start merely because
their declarations appear in a catalogue. A declared address also does not
establish that a selected record actually contains one.

The review found request readers that could omit user MCP tools or restore tools
from a global catalogue after the request catalogue had explicitly become empty.
Generic content types could create arbitrary dependencies, while some reference
paths described a collection where a consumer required one scalar value.
These defects affect planning, parameter protection and autonomous execution,
so they require a shared contract rather than separate prompt examples.

## Decision

1. **The available request manifests define semantic producers and consumers.**
   An explicitly empty catalogue remains empty. Ontology editorial links are
   resolved against the tools actually available to this request. The ontology
   retains its validated hierarchy, properties and inverses; this decision
   introduces no general OWL reasoner or unused similarity machinery.
2. **Shape, semantic value type and business role are separate contracts.**
   A field can publish its role, admitted value types, entity types and
   predicates. Reference suggestions check the declared scalar, array or object
   shape; parameter guards inspect nested annotated leaves and applicable schema
   branches. This is not a universal runtime payload validator. Generic content such as
   `Text` or `QuantitativeValue` does not authorize automatic substitution or
   create a cross-domain prerequisite by itself.
3. **Only canonical observed values supply field proof.** A binding identifies
   the exact account, selected registry entity, source reference, parameter
   path, unchanged typed value, semantic type, entity type, predicate and role.
   The server independently reconstructs the source observation and checks the
   binding against it. A planner label, text equality, unselected record,
   optional missing field or declared future output cannot manufacture proof.
   Values remain unchanged; evidence is carried beside them.
4. **Closure retains constructible read-source chains.** The catalogue computes
   a finite fixed point from sources whose semantic prerequisites can start,
   preserves their complete ancestors in execution order, and exposes absent
   sources and unseeded cycles as gaps. Only independently validated parameter
   seeds remove prerequisites. The initial filter has no concrete parameters
   and cannot invent seeds. Closure establishes a declared path, not success of
   a future remote operation or an arbitrary complete execution plan.
5. **Mutation attempts delimit proof freshness.** Both execution modes invalidate
   earlier source proof immediately before a mutating or delegated invocation
   and again on completion, including failure. The second boundary rejects a
   read that completed during an in-flight mutation. A rejected guard before
   invocation does not pretend a remote mutation occurred. Pipeline execution
   owns its serializable plan-local proof clock; historical registry cards are
   retained without conferring fresh proof.

Product taxonomy adjacency remains distinct from executable dependencies: a
domain triangle can be valid even though an execution dependency cycle cannot.
The exact request-tool ownership boundary is specified by
[ADR-338](ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md).

## Considered options and trade-offs

| Option | Benefit | Reason for the decision |
|---|---|---|
| Type or text equality alone | Small prompts and simple matching | Cannot distinguish a person's address from an unrelated place or a field from its container |
| Any declared producer closes a dependency | Cheap catalogue expansion | Accepts self-dependencies and unseeded cycles; a path may have no executable start |
| General ontology inference | Expressive relation discovery | More inference does not establish account ownership, selected values or observation freshness |
| Canonical field proof and constructive closure | Traceable relation meaning and executable source order | Selected; needs explicit contracts and conservatively leaves uncertain relationships unresolved |

## Consequences

Cross-domain links become reviewable at the actual field and source. Tools that
lack a useful semantic annotation retain their structural JSON contract; adding
a generic annotation solely to improve coverage would weaken this decision.
User-specific MCP business meaning remains unknown unless its live declaration
provides an admitted contract. Mutation invalidation can require another read,
which trades extra work for avoiding a stale justification.

The implementation does not claim complete semantic coverage, universal unit
conversion or optimal routing. The evolving inventory and remaining gaps are
recorded in the qualification reports rather than fixed as architectural counts.

## Validation and follow-up

The [execution qualification](../technical/SEMANTIC_EVOLUTION_QUALIFICATION.md)
records independent structural before/after oracles, mutation races and the
remaining limits. The [taxonomy qualification](../technical/TAXONOMY_QUALIFICATION.md)
records the current annotation inventory and request-identity checks.

The maintained entry points are `task semantic:audit` and
`task semantic:simulate`. Representative contracts are exercised in
[semantic value binding tests](../../apps/api/tests/unit/domains/agents/semantic/test_semantic_value_bindings.py),
[constructible source tests](../../apps/api/tests/unit/domains/agents/services/catalogue/test_constructive_source_paths.py)
and [pipeline proof tests](../../apps/api/tests/unit/domains/agents/orchestration/test_pipeline_semantic_proof_scope.py).
New relations must add a concrete producer/consumer observation and a failing
counterexample before broadening the admitted contract.

## Implementation references

- [Field contracts](../../apps/api/src/domains/agents/registry/value_contracts.py)
- [Canonical value bindings](../../apps/api/src/domains/agents/semantic/value_bindings.py)
- [Registry observations](../../apps/api/src/domains/agents/semantic/registry_value_bindings.py)
- [Constructible source paths](../../apps/api/src/domains/agents/services/catalogue/source_paths.py)
- [Plan proof scope](../../apps/api/src/domains/agents/semantic/plan_proof_scope.py)
