# ADR-338 — Live MCP contracts and exact callable identity

**Status:** Accepted — implemented and qualified locally; deployment is not certified.
**Date:** 2026-10-07
**Deciders:** The owner authorized semantic/MCP review and taxonomy improvements;
Codex recorded the implementation choices and their measured limits.
**Scope:** MCP discovery, manifests, routing, callable resolution, delegation and confirmation.

**Amends:** [ADR-070](ADR-070-ReAct-Execution-Mode.md),
[ADR-255](ADR-255-MCP-Tool-Declaration-Conformance.md) and
[ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md).
**Related:** [ADR-224](ADR-224-Conformite-MCP-2026-07-28-SDK-v2.md),
[ADR-335](ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md) and
[ADR-337](ADR-337-Checkpointed-ReAct-Read-Segments-And-Turn-Local-Reuse.md).

## Context and problem statement

User MCP servers and their objects cannot be enumerated before each person's
connection. Their current declared schema is the available contract. A stored
summary can lag behind discovery; a hot connection can keep an old catalogue
alive; failed construction can leave a domain advertised without a callable tool.

Routing slugs and model-facing function names have different constraints from
server identifiers and RPC verbs. Normalization can merge two admin keys or
truncate two user UUIDs to the same prefix. Resolving such aliases from a global
registry can dispatch outside the offered request catalogue. A per-server
delegation callable can also be supplied another server in its parameters unless
the callable binds its own target before confirmation.

## Decision

1. **Read the current declaration, without inventing business meaning.** Preserve
   MCP `outputSchema` and `structuredContent`, compositions, nullability and
   explicit constraints. Only admitted semantic annotations and explicit formats
   supply semantic leaves; names such as `id` or `address` are insufficient.
   Invalid declared values retain their raw data and expose bounded unusable-path
   observations. Missing schema or uncertain alternatives remain unknown.
   External content remains external after projection.
2. **Age and fingerprint describe the discovered contract.** Schema age expires
   independently of connection idle time. Account/server connection settings,
   canonical schema and descriptions govern contract fingerprints; tool token
   estimates and embeddings follow the current contract. Failed refresh does
   not make an old contract fresh. User discovery is cached within a worker;
   execution connections are ephemeral. Fingerprinted user embedding envelopes
   persist in the database. These mechanisms are not distributed result
   coherence. Admin snapshots reflect effective registration, rather than
   promising hot discovery on every request.
3. **Publish usable request capabilities.** Only successfully constructed,
   assistant-visible callables publish routing domains and agent tool lists.
   Failed, empty or app-only catalogues do not advertise an executable domain or
   delegation proxy. Partially buildable catalogues name only registered tools.
   An explicitly empty request cannot resurrect a generic MCP fallback.
4. **Separate three namespaces.** Trusted manifest metadata records admin/user
   origin and the exact admin server key or full user-server UUID. Domain slugs
   and bounded model-facing callable aliases are separately allocated, with
   collisions detected against existing native/admin/user names. Original RPC
   verbs and full runtime identifiers remain unchanged. Disable preferences,
   account ownership, adapter/resource identity and confirmation labels use the
   appropriate exact identity, never a normalized prefix heuristic.
5. **Resolve within the offered request contract.** Execution and semantic readers
   first consult the offered manifest and verify the actual adapter or task
   owner. Ambiguous aliases and empty bound catalogues are refused. In a bound
   request, this replaces ADR-070's historical global/suffix lookup precedence.
   Outside a bound snapshot, legacy lookup remains for compatibility. Offered-owner
   isolation applies to execution paths that install the request snapshot; an
   explicitly empty snapshot never falls back. Deferred draft confirmation uses
   the same resolver and ownership boundary when the snapshot is bound.
6. **Bind a delegation's target before admission.** A server-specific task checks
   its exact server target and user prefix before policy lookup, HITL creation or
   invocation, including after rename or gate reinstallation. Valid calls cross
   exactly one current centralized effect gate. `delegates_execution` is explicit:
   a report from hidden inner execution does not prove each read/write and cannot
   enter read reuse, independent-read concurrency or read-only gap recovery.
7. **Project fresh capabilities beside stored operator text.** User MCP routing
   descriptions append current usable capabilities with bounded omission
   disclosure. Historical description provenance remains unknown: this projection
   neither rewrites database rows nor labels an old summary as regenerated.
   Ephemeral source markers and fingerprints distinguish current declarations
   from stored text. Capability descriptions preserve literal URLs.

## Considered options and trade-offs

| Option | Benefit | Reason for the decision |
|---|---|---|
| A universal predefined user-MCP ontology | Simple static catalogue | User servers, schemas and account permissions are not predictable |
| Use normalized slugs/function names as identity | One convenient namespace | Collisions can change routing, preferences, ownership or confirmation target |
| Fall back to global tool lookup | Apparent availability after discovery gaps | Can execute a tool outside the offered account/request contract |
| Infer inner actions from a delegated summary | More apparent completion | Neither annotations nor prose establish individual observed effects |
| Live declarations with exact identity and bound request resolution | Preserves usable capability without alias-based authority | Selected; uncertain schemas and ambiguous ownership are refused or remain unknown |

## Consequences

New user servers become reachable from their actual usable declarations without
pretending to know their business ontology beforehand. A routing alias can change
without changing the runtime server or RPC. Confirmation names the real target,
and a model cannot redirect a server-specific callable by changing its parameters.
Schema refresh and rejection require observability; the MCP quality/cache metrics
and dashboard expose these boundaries.

Declared MCP schemas and annotations remain statements from an external server,
not proof of every future output or hidden action. Provider-specific schema
translation, deep/unsupported references and arbitrary user servers retain the
limits documented in the qualification reports. No production-server effects
were exercised by the isolated contract fixtures.

## Validation and follow-up

The [taxonomy qualification](../technical/TAXONOMY_QUALIFICATION.md) and its
[recorded evidence](../superpowers/qualification/taxonomy-2026-10-07.json) cover
slug/UUID/RPC collisions, exact disable keys, empty and partial publication,
semantic-reader ownership, bounded aliases, task targets and confirmation labels.
The [execution qualification](../technical/SEMANTIC_EVOLUTION_QUALIFICATION.md)
covers schema refresh, account scope and declared-output observations.

Representative tests cover
[callable identity](../../apps/api/tests/unit/infrastructure/mcp/test_callable_identity.py)
and [delegation targets](../../apps/api/tests/unit/infrastructure/mcp/test_task_identity.py).
Additional server dialects must extend these observations rather than bypass
ownership checks or infer a business type from a suggestive field name.

## Implementation references

- [Request identity](../../apps/api/src/domains/agents/registry/request_tool_identity.py)
- [MCP domain allocation](../../apps/api/src/domains/agents/registry/mcp_domains.py)
- [Offered manifest resolution](../../apps/api/src/domains/agents/registry/manifest_resolution.py)
- [Callable resolution](../../apps/api/src/domains/agents/tools/tool_resolution.py)
- [Delegation identity](../../apps/api/src/infrastructure/mcp/task_identity.py)
- [Registration aliases](../../apps/api/src/infrastructure/mcp/registration_aliases.py)
- [User catalogue projection](../../apps/api/src/infrastructure/mcp/user_catalogue.py)
- [Schema contract projection](../../apps/api/src/infrastructure/mcp/semantic_schema.py)

## Amendment 2026-10-28 — a personal server's catalogue is a snapshot (ADR-366)

For PERSONAL MCP servers only, a turn no longer discovers the catalogue live when the account's
snapshot is valid or merely aged: the snapshot is served while one worker revalidates it, servers
are prepared in parallel under a ceiling, and a server still preparing is left out of that turn
without being cancelled (owner decisions Q1 and Q2 (a)). The exact callable identity of §2 is
checked where it matters — at the moment of the call (`declaration_check.py`): a withdrawn tool, a
rejected argument or a tightened declaration refuses the call before it is sent. See
[ADR-366](ADR-366-Personal-MCP-Catalogue-Snapshot-Served-While-Revalidated-Verified-At-Use.md).
