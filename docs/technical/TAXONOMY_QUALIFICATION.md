# Taxonomy corrections and full-menu routing qualification

Measured in the shared development checkout on 2026-10-06 UTC / 2026-10-07
Europe/Paris. Changes are local. This extends the
[semantic execution qualification](SEMANTIC_EVOLUTION_QUALIFICATION.md); it does
not certify deployment or a globally optimal ontology.

La [recette manuelle](SEMANTIC_MANUAL_ACCEPTANCE.md) propose les parcours à vérifier
dans l'application, avec données contrôlées, prompts et critères de résultat.

[ADR-338](../architecture/ADR-338-Live-MCP-Contracts-And-Exact-Callable-Identity.md)
records the live-contract, publication and exact-identity decisions;
[ADR-335](../architecture/ADR-335-Canonical-Semantic-Proofs-And-Constructible-Dependencies.md)
records the distinct semantic-proof and execution-dependency boundary.

The [recorded evidence](../superpowers/qualification/taxonomy-2026-10-07.json)
contains the static inventory, exact domain menus, independent expectations,
original and qualified decisions, database configurations, tariffs and all paid
attempts. Failures remain failures under the same business oracle.

## Taxonomic coverage and corrections

The measured inventory contains 35 static domains, including 32 routable entries.
One is the virtual MCP fallback; the full native routing menu contains 31 domains.
Every native routable domain has an independent request in
`apps/api/scripts/semantic_simulation/taxonomy_corpus.py`.
Internal context, query and sub-agent domains have explicit exclusions. Python
is a platform capability, and location results are auxiliary to the place domain.
Tool agents and result keys have no unexplained native taxonomy orphan.

Image generation now advertises editing as well as creation. Availability tests
derive the setting-domain feature flag from its declaration. The setting agent
remains deliberately excluded from generated skill templates pending a separate
exposure design; its ordinary runtime availability is unchanged. Static manifest
collection succeeds in an isolated process without importing the application
first: a typed lazy briefing-router export removes the masked import cycle.

The measured product graph contains 20 adjacencies. These express useful domain
relationships, not executable prerequisites. A triangle is legitimate; duplicate
reciprocal declarations are rejected. Execution dependencies retain their own DAG
validation.

MCP routing now keeps an exact configured admin key separate from its routing
alias. Disable preferences use that exact key, including colliding normalized
names. Domain allocation reserves natural suffixed names, native entries and
admin domains before allocating user aliases. The manifest carries trusted origin
and server identity, which also enter read-reuse signatures.

Callable lookup uses the offered request contract and checks the actual adapter
or task owner. Ambiguous aliases and explicitly empty catalogues are refused.
User UUID prefixes extend when they collide; admin key/RPC combinations allocate
distinct aliases, preserving the original RPC and server key. Invalid or oversized
model-facing aliases are bounded separately from those identities. The same
ownership boundary applies to semantic readers and deferred confirmations.
Per-server delegation callables also bind their target parameters, so naming one
task cannot authorize dispatch to a different server supplied in its arguments.
Incorrect targets fail before policy lookup, confirmation creation or invocation,
including after a task is renamed or its gate is installed again. Valid targets
still cross exactly one effect gate under the current alias. Confirmation labels
identify the real server and original RPC rather than a technical alias hash.

Failed, empty and app-only servers publish no usable routing domain. An explicitly
empty request catalogue cannot resurrect the generic MCP domain. Actual user
discovery, request-manifest construction and analyzer-menu tests cover these
publication boundaries for standard and iterative servers.

Fresh user MCP projections append the currently discovered usable capabilities
to stored operator text. Historical description provenance is unknown: this
change does not label an old summary as custom or generated, rewrite database
rows, or claim an old summary itself has been regenerated. Current declaration
fingerprints and ephemeral source markers make that distinction observable.
Bounded descriptions include all short capabilities, retain periods inside URLs,
and disclose omissions when a large catalogue exceeds the description budget.

The six initial regression failures covered generated/literal slug collisions,
raw disabled keys, failed-server publication, empty generic MCP availability, a
missing sixth capability and URL-period truncation. Their fixtures use the actual
manifest factory signature; an earlier fixture-error run is excluded from the
baseline.

Additional callable-identity scenarios reproduce nine failures before correction.
The semantic-reader corpus reproduces twelve failures among eighteen independent
cases before correction; all eighteen pass afterward. These are isolated real
construction, context and resolution paths, with no external server effect.

Admin registration also tests partially buildable catalogues: an agent names only
its successfully registered visible tools, and no domain or iterative proxy is
published without a callable capability. A genuinely callable reference tool can
remain available to an iterative server; preloaded references excluded from the
standard tool menu do not manufacture availability.

## Semantic annotation remains a separate measure

The static audit measures 137 tools, 214 semantically annotated parameters out of
400, and 392 annotated output fields out of 685. It resolves 93 used types against
121 ontology types and 44 properties, with no unknown annotation or ontology
integrity error. These are snapshot observations, retained in the evidence file.

Complete domain classification does not mean every attribute has complete
business semantics. Transport flags, heterogeneous containers and free text may
remain structurally typed without establishing cross-domain entity identity.
Unknown user MCP meanings still require discovery and canonical observations.

## Real analyzer decisions with the full menu

The independent corpus contains 48 cases: every native routable domain, compound
requests, distinctions between similar stores, city/person homonyms, six languages
and standard, admin, disabled and iterative MCP fixtures. Every native menu
contains all 31 native domains; a usable fixture server adds one MCP domain.
Cases never narrow the menu to their expected answer.

Each paid call uses the production analyzer prompt, structured contract and shared
availability policy. Explicit model and provider rows are required in the
development database and checked again before each call. The configured analyzer
resolved to DeepSeek deepseek-flash at its effective configured sampling. Inherited
sampling fields are disclosed in the artifact. Model and SDK retries are disabled;
an unknown paid usage stops further probes.

| Observation | Full-menu reference | Qualified instructions |
|---|---:|---:|
| Required domains and mutation intent correct | 48/48 | 48/48 |
| Strict scope and primary-domain priority correct | 41/48 | 44/48 |
| Paid calls | 48 | 48 |
| Settled cost EUR | 0.011430011 | 0.013334783 |

The general instructions now prioritize the requested final operation over its
prerequisite lookup, preserve every independent requested result, and avoid
alternative sources selected only for similar capabilities. A stored future
automation instruction is distinguished from an operation requested now.

The four remaining strict failures are explicit: two requests add web search for
the contents of a future automation, and two event-to-weather/route chains choose
the prerequisite event as primary. Both chains retain their necessary target
domain. These results qualify the analyzer decision, not downstream workflow
success. No unavailable domain survives or appears in the qualified raw choices.

The probe distinguishes raw model failures from selections cleaned by the
availability policy. It refuses unexpected or multiple structured calls and
provider-reported truncated output, even when a shortened object can be parsed.
Its tests also ensure that invalid cumulative budgets stop before preparation,
and that a paid failure is saved before the run stops.

There is one sample per case and phase at configured sampling. The observed score
change is not statistical or causal proof. The second phase costs more, so no
global model-cost or latency reduction is claimed. These two phases spend EUR
0.024764794 across 96 calls; including the prior campaign, the recorded total is
EUR 0.071473504 across 227 calls, within the authorized cumulative EUR 2 ceiling.

## Reproduction and limits

`task semantic:audit` refreshes the static inventory. `task semantic:simulate`
includes the independent taxonomy corpus and monetary/structured-output guards
without making provider calls. Full-menu export uses
`python -m scripts.semantic_simulation.taxonomy_run --prior-spend-eur <recorded-total>`
inside the configured API environment. For paid evaluation, add
`--real-models`, set `--budget-eur` and supply an accurate previous campaign total;
`--case` supports an explicitly scoped replay. The script requires existing
database routing and tariffs; it never substitutes a default model.

Feature availability and MCP servers are controlled fictional fixtures. Native
or MCP tools are never invoked by the paid probes. Account permissions, skills,
conversation history, peer directories, the full router state machine,
planner/ReAct full-menu workflows, external provider accuracy and arbitrary user
MCP schemas are outside this evaluation. The prior ReAct observation that a model
can shorten an event's street location to its city also remains a separate limit.

The targeted semantic/orchestration suite passes 2,246 tests with one
configuration-dependent timeout case skipped. The simulation task passes 215
cases. The integration suite passes 3,687 tests; a final check after source
extraction passes 1,686 MCP/registry/identity/confirmation and harness tests.
These suites overlap and their counts must not be summed. Targeted type
checks and formatting pass; dependency cycles remain within their baseline.
At that phase's snapshot, global documentation preview found unmapped concurrent
infrastructure modules, account_preferences and personalization, and the global
complexity check regressed in concurrently edited application, memory and journal
code. The subsequent ADR review below records the refreshed verdict; these
historical observations do not certify a clean global CI run.

## ADR review follow-up on 2026-10-07

ADR-335 through ADR-338 now record the architectural choices, alternatives,
implementation references, evidence and remaining limits. Their index, history
entries in all six site languages, generated maps and derived public counts are
synchronized. Concurrent infrastructure modules are explicitly attached to
their existing API, Live, push and telephony map bricks, without changing their runtime code.
Documentation preview, release surfaces, i18n and the full frontend lint/type
gate pass. The refreshed complexity and runtime-cycle gates also pass without
raising either baseline.

The ADR review exposed one further real publication defect: an admin iterative
proxy whose import failed still published a manifest, agent and domain. Task
registration now reports success explicitly; a failed proxy is counted and
publishes none of those capabilities, while a healthy sibling remains available.
The isolated reproduction changes from three failures to three passes, and the
expanded MCP suite passes 161 cases. Its observations and limits are retained
under `component_qualification.admin_iterative_proxy_construction` in the
recorded evidence.

The global pass also exposed stale selector fixtures that lacked the current MCP
identity contract. The three selector test files now construct real manifests,
adapters and task callables; their selection, ranking, cap and approval assertions
are unchanged. All 43 selector tests pass. These counts overlap other suites and
must not be added to their totals. No paid model call was made for this follow-up.

MCP confirmation labels now use the reader's language separator while retaining
the exact server and RPC. The obsolete punctuation-guard exception is removed;
154 label, identity and confirmation tests pass, with no new exception added.

The final global fast-backend run, using a fresh temporary directory outside the
repository, reports **38,449 passed, 15 failed and 150 skipped**. Two failures
judge the actual Git index, which still excludes the unstaged new source and ADRs;
the documentation preview passes. The remaining failures concern concurrent
application/extraction and delivery-authority/heartbeat contracts, including the
development database missing a newly added user column and stale fixtures. Global
Ruff still reports twelve concurrent import/style errors; the targeted sources
and fixtures pass. The exact failed test identities are retained in
`verification.architectural_records` in the evidence. This remains a local
qualification, not certification of a clean global CI or deployment.
