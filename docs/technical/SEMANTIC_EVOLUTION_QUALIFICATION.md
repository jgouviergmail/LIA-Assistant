# Semantic execution improvements and qualification

Measured on 2026-10-06 in the shared development checkout. This extends the
[contract review](SEMANTIC_CONTRACT_REVIEW.md) and
[initial simulations](SEMANTIC_SIMULATION_RESULTS.md). Changes are local; this
report does not certify deployment or all possible user MCP servers.

Architectural decisions are recorded in
[ADR-335](../architecture/ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md)
(field proof and constructible closure),
[ADR-336](../architecture/ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md)
(verified requested outcomes),
[ADR-337](../architecture/ADR-337-Checkpointed-ReAct-Read-Segments-And-Turn-Local-Reuse.md)
(checkpointed reads and reuse) and
[ADR-338](../architecture/ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md)
(live MCP contracts and callable identity).

This is a phase snapshot. The subsequent
[taxonomy qualification](TAXONOMY_QUALIFICATION.md) records the updated static
inventory and real analyzer decisions against the full domain menu.

The [component observations](../superpowers/qualification/semantic-components-2026-10-06.json)
retain the structural before/after oracles and execution counters. Component test
suites overlap and their counts must not be summed.

## Implemented behavior

Field contracts now publish their role, admissible value types, entity types and
predicates to the planner. Canonical observations identify the account, source,
selected registry entity and exact value. A planner-authored label or equality of
text cannot manufacture that proof. A city named Nancy does not establish the
address of a person named Nancy. Optional fields remain optional.

Dependency closure chooses constructible provider chains, retains their ancestors
in executable order, and reports unseeded cycles and absent sources. It never
counts a declared output as an observed parameter seed. Thirteen structural
oracles using recorded pre-change implementations pass in four cases before the
change and all thirteen afterward. The initial filtering stage still lacks
concrete parameters: it publishes gaps rather than fabricating seeds.

User MCP discovery expires by schema age independently of idle time. Canonical
schema, descriptions, connection settings and account scope govern cache
fingerprints; embeddings and tool-token estimates follow the current contract.
Six initially failing regression cases now pass. The expanded MCP optimization
corpus contains twenty cases, including refresh in flight, concurrent discovery,
separate accounts, nullability, format observations and failed refresh. Invalid
declared values retain their original data and expose bounded unusable-path
observations. The new cache and semantic-quality metrics have Grafana panels.

ReAct checkpoints each independent read segment before a potential interruption.
Only explicitly eligible independent reads run concurrently. Fresh exact reads
can be reused within the same account, thread, turn and runtime context. Changes
to schema, refresh requests, expiration and attempted mutations invalidate reuse.
Both execution modes invalidate field proofs at mutation start and completion,
including failures and a concurrent read that finishes before mutation completion.
Budget checks run between segments, and every abandoned call receives its closing
ToolMessage. Sandbox registry data reaches Python as usable JSON, and its budget
survives a resume in another graph instance.

The analyzer now extracts explicit requested outcomes, anchored to the current
request. Literal values, counts, dates, operation kinds and same-item constraints
are checked against canonical tool observations. A draft is pending; an opaque
result cannot prove completion. MCP safety annotations do not prove an action
verb. Partial markers in metadata override completeness claims in data. Recovery
passes remain bounded and read-only. Requested-result evidence stores compact
constraint-specific verdicts and counts rather than duplicating the raw payload.
Final synthesis receives the verified gaps even if the model omitted them.

The MCP iterative factory explicitly marks delegated execution. A delegated
report cannot establish individual reads or writes and remains unknown; its
failure cannot turn it into a retryable read. Individual MCP tools still use their
declared contracts. Literal boundaries distinguish names, decimal values,
mailboxes and complete URLs from prefixes of a different requested value.

Date expectations use the server's request day and timezone, retained across a
checkpoint resume. Civil dates keep their calendar day; offset timestamps are
converted to the request timezone. A malformed date prefix cannot corroborate a
different date. Five independent date oracles pass in one case before the fix and
all five afterward.

The static inventory at the end of this phase contains 131 tool manifests, 214 semantically annotated
parameters out of 394, and 392 annotated output fields out of 676. It resolves 93
used types against 121 ontology types and 44 properties, with no unknown annotation
or ontology-integrity error. Those counts describe annotations, not complete
business meaning: free text and heterogeneous containers do not become reliable
cross-domain identities just because they receive a generic type.

The real-model corpus also exposed a validator bug: a bare reference prefix inside
literal prose was treated as a dependency. The validator now distinguishes that
mention from an executable field reference and traverses nested batch parameters.

## Observed execution efficiency

| Controlled case | Result |
|---|---|
| Two identical fresh reads | One call, two correctly paired ToolMessages |
| Two reads then HITL, resumed in a new graph | Two total read calls, one write; no read replay |
| Nine independent reads | Nine calls; maximum concurrency four; nine registry items |
| Five reads with budget exhausted after first segment | Four calls; the fifth is abandoned and explicitly closed |
| Eight identical reads with a 50 ms fixture delay | Serial 0.5138 s; concurrent 0.1714 s; equal canonical outputs |

These are actual native execution and checkpoint paths with isolated provider
fixtures. The latency row is one controlled observation, not a production or
end-to-end assistant latency claim. Unknown, interruptible and mutating tools
retain sequential execution.

## Real configured models

The [recorded comparison](../superpowers/qualification/semantic-evolution-2026-10-06.json)
contains the exact effective provider/model configurations, inherited sampling
fields, database tariffs, paid call counts and original versus comparable grades.
Every slot required an explicit provider and model in the development database;
identity was checked again before each call. The configured analyzer, planner and
ReAct slots all resolved to DeepSeek deepseek-flash in this instance. SDK retries
were disabled and calls conservatively bounded against the authorized ceiling.
No external native tool or account mutation was executed by the model probes.

| Phase | Comparable correct decisions | Paid calls | Cost EUR |
|---|---:|---:|---:|
| Controlled analyzer reference | 20/24 | 31 | 0.010800 |
| Real analyzer and requested-result hints | 23/24 | 43 | 0.015729 |
| Precision instructions and reference fix | 23/24 | 43 | 0.015275 |

All phases are graded with the same independent business oracle. Valid ISO
date/datetime forms and harmless comma whitespace are equivalent; fictional
address aliases are explicitly listed. Old validation/execution failures remain
failures. Original stricter grades are retained in the comparison. There is one
sample per case, mode and phase at the configured temperatures; this is not a
statistical or causal proof of improvement. The additional analyzer call costs
more than the controlled reference, so no global model-cost reduction is claimed.

Including the previous campaign, actual settled spend is approximately EUR
0.046709 for 131 provider calls, within the authorized cumulative EUR 2 ceiling.

## Remaining limits and verification

One real-model case still fails: ReAct shortens an event's full street location to
its city when requesting its forecast. The planner retains the full location in
that case. A general deterministic check of the requested source entity/field
would be needed to prevent that approximation in every autonomous call.

The narrowed catalogue and fictional observations qualify real model decisions,
not full routing, tool selection, external provider accuracy, production data or
every language. Goal extraction is still a model interpretation; literal anchors
constrain it but do not formally prove every natural-language intent. Independent
pages without a verified page chain/entity identity remain unknown when their
combined count could satisfy a request. Ambiguous raw scalars require selected
canonical source evidence or clarification. No general new planner bypass or
adaptive pipeline mutation recovery was added.

The administrative MCP registry is still discovered at startup. The MCP SDK may
perform its own discovery. Google provider conversion does not enforce every
JSON Schema assertion: the original assertions remain published, with remaining
constraints described explicitly. User-specific domain meanings cannot be known
before discovering their contracts and actual outputs.

Targeted qualification covers semantic/catalogue/pipeline, MCP, native ReAct,
checkpoint, truncation, sandbox and monetary-bound oracles. Type checks, formatting,
complexity, size, dependency-cycle and observability guards were also run. The
initial broad unit run reported 37,668 passes, 14 failures and 150 skips. Findings
introduced by this change are repaired and rechecked separately. The combined
targeted run reported 4,217 passes, one skip, and one global size-guard failure in
the concurrently changed memory extractor. A separate rerun of the broader
findings retained eight failures in application contracts, release counts,
dependency declarations, an empty exception handler and that size guard. The
semantic simulation task passed its 94 cases. Documentation preview passed links
and facts but found an unmapped concurrent infrastructure module, personalization.
These findings prevent claiming a clean global CI run. The final response reports
the latest verification outcome rather than treating the broad run as green.
