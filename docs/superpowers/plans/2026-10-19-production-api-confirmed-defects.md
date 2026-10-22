# Production API confirmed defects implementation plan

> **For agentic workers:** Use systematic debugging, test driven development and verification before completion for each independent fix.

**Goal:** Correct the confirmed production-log defects, prioritising independent skill, MCP and plugin sharing, with regression evidence and no production operation.

**Architecture:** Preserve the existing native import, ownership, HITL, transaction, tool and provider boundaries. Fix each failed boundary at its source and test the production semantics rather than replacing them with simplified mocks.

**Tech stack:** FastAPI, SQLAlchemy, PostgreSQL, LangChain, pytest, Next.js and Vitest.

**Spec:** User request of 19 October 2026 and the locally retained production API diagnosis. The diagnosis contains private raw evidence and stays under the ignored `.tmp` directory; tests use fictional inputs only.

## Global constraints

- Preserve every pre-existing staged and unstaged modification. No resets, broad formatting, staging, commits or pushes.
- No production or demo production deployment, restart, seed, migration or configuration mutation.
- Regression first, then the smallest fix, then focused and repository-required checks.
- Database tests use disposable PostgreSQL; no developer or production data cleanup.
- Keep disabled received copies, credential exclusion, ownership, provenance and mutation approvals.
- Preserve rejection of invalid provider data; never weaken schema, privacy or quota guards.

## Review focus

- A new recipient has no skill state yet; retries must preserve recipient edits and create no duplicate.
- Plugin children and MCP copies must retain native collision, credential and activation rules.
- MCP calls must preserve admitted dynamic properties and wire aliases without collisions with generated Python field names, on all invocation paths.
- Schema exceptions and nested tracebacks must not quote user data above DEBUG.
- Numeric Gmail timestamps must stay distinct from ISO calendar dates and RFC mail dates.
- Permanent provider refusals must not retry; transient transport faults must retain their bounded recovery.

## Task 1 Native sharing

Files: `skills/preference_service.py`, peer transfer integration tests and existing sharing browser journey as needed.

- [x] Reproduce new skill installation failure using `autoflush=False` in the real transfer fixture.
- [x] Flush the newly created recipient state before registration hooks read it, within the existing transaction.
- [x] Verify skill, plugin with skill children and MCP transfer ownership, disabled state, secret exclusion, retries and rollback against disposable PostgreSQL.
- [x] Exercise the existing settings journey for all three native kinds with hermetic API traffic.

## Task 2 Execution and provider errors

Files: `agents/nodes/react_egress_question.py`, `llm/structured_output.py`, voice provider adapters, meetings transcription and their tests.

- [x] Reproduce out-of-schema ReAct arguments reaching Python; validate before direct invocation and return a typed invalid-input outcome.
- [x] Reproduce deterministic Anthropic HTTP400 retries; preserve the typed refusal and retain bounded transient retries.
- [x] Reproduce too-short audio and Edge HTTP403 losing permanent failure classification; retain safe vendor/status facts.
- [x] Verify successful egress/HITL settlement and valid tool invocations remain unchanged.

## Task 3 Privacy dates and attribution

Files: `core/time_parsing.py`, observability quoted-content filter, LLM callbacks and associated tests.

- [x] Reproduce numeric millisecond strings interpreted as ISO; recognise numeric timestamps before ISO and retain existing date families.
- [x] Reproduce quoted jsonschema instance data surviving the log sanitizer; redact it centrally including nested tracebacks.
- [x] Reproduce LLM callbacks labelling known models as unknown; resolve from declared invocation metadata/model attributes without exposing provider secrets.
- [x] Verify logs retain bounded error facts and ordinary technical errors remain useful.

## Task 4 Startup and scheduler

Files: startup config caches, LLM config cache, scheduled action executor, tests in the corresponding unit directories.

- [x] Reproduce successful cache loading misreported as CRITICAL and skipped failover validation; separate failures and validate the effective deployment slots.
- [x] Reproduce unused Ollama URL triggering discovery; discover automatically only when the effective configuration needs Ollama, preserving explicit admin discovery.
- [x] Reproduce unavailable routine owner leaving a live reservation; settle safely without executing the action.
- [x] Reproduce timeout outcomes labelled refused by parsing prose; preserve the typed run outcome.

## Task 5 Normal lifecycle and diagnostics

Files: presence telemetry, profile image requester, routing/readability logging and focused tests.

- [x] Reproduce presence/image requests from inactive accounts; gate auxiliary requests on activation while retaining server authorization.
- [x] Classify successful readability recovery and medium-confidence valid routing at an appropriate level; retain warnings for actual failures.
- [x] Where a confirmed logging defect hides an exception category, add bounded reason/type facts without request bodies or provider prose.

## Verification

- [x] Record red/green results for each defect and review the complete new diff separately from the initial staged work.
- [x] Run affected PostgreSQL sharing integration tests and hermetic browser journey.
- [x] Run `task lint`, `task test:backend:unit:fast`, `task test:backend:agents`, `task test:frontend` and frontend coverage for the touched UI paths (the coverage task runs the complete frontend suite).
- [x] Run `task test:backend:unit:coverage` sequentially for the background-execution changes, preserving its official coverage floor.
- [x] Preserve and report any inherited failures with exact command, count and warning context; fix root causes in scope without lowering gates.
- [x] Reconcile every confirmed defect with its implementation and evidence; list external causes requiring operator configuration separately.

Final evidence: 38 sharing PostgreSQL tests and 6 desktop/mobile browser journeys pass; backend fast and sequential coverage each pass 44,902 tests with 31 expected skips (coverage also deselects 9). Backend coverage is 79.36%, above the unchanged 78% floor. The agents suite passes 1,101 tests and frontend coverage passes all 13,297 tests. Global lint, final Python lint, complexity, cycles and CI marker coverage pass. Detailed command logs, earlier red results, external limitations and cleanup evidence remain in the private ignored audit directory. All disposable services created for this intervention were removed; production and demo production were not deployed or mutated.
