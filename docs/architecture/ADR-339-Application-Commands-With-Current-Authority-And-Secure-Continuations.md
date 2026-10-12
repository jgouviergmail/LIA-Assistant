# ADR-339 — Application commands with current authority and secure continuations

**Status:** Accepted — implemented; local qualification does not certify every device or deployment.
**Date:** 2026-10-12
**Scope:** Conversational application management, durable commands and browser continuations.

**Related:** [ADR-263](ADR-263-Execution-Authority-Chain-And-Effect-Register.md),
[ADR-336](ADR-336-Requested-Outcomes-Checked-Against-Canonical-Observations.md),
[design specification](../superpowers/specs/2026-10-06-lia-application-tools-design.md)
and [technical guide](../technical/APPLICATION_COMMANDS.md).

## Context

Managing LIA through conversation spans account preferences, connected resources,
administrative capabilities and operations that require the person's browser or
private input. Discovering a route does not grant permission to call it. A draft
can outlive a role change, an operator switch, its schema, or the originating
session. A successful handoff is not proof that the awaiting action committed.

## Decision

1. **Declare reviewed operations.** `ApplicationOperationSpec` owns operation
   identity, tool name, UI sections, input/output schema, read/action/device/secure
   kind, administrative scope and required platform capabilities. Request-visible
   catalogues derive from these declarations and current account authority.
   The reviewed preference-field vocabulary prevents a new API field from
   silently becoming a credential-bearing model parameter.
2. **Recheck current authority at execution boundaries.** Fresh database reads
   verify the actor is active, owns the target and, where required, is an
   administrator. The persisted platform switch and required capabilities fail
   closed. Model-supplied user IDs or stale role snapshots do not authorize an
   action. Schema version/fingerprint, canonical intent and expiry must still match.
3. **Bind approval to an exact durable command.** Conversational mutations use
   the native application action draft and strict shared effect gate. Its
   actor, draft, operation, before/after values, expected digest, schema and
   expiry form the approved content. `application_commands` persists encrypted
   content/result/origin binding, a digest, phase and fenced claim token.
   Owner-conditioned claim and settlement prevent an unrelated or duplicate
   execution from closing a command. Direct manual UI controls retain their
   existing contracts; this decision does not add conversational approval to
   every ordinary settings click.
4. **Continue sensitive/device work through its real owner.** The authenticated
   `/application-commands` routes derive browser identity from the actual
   session and, for an addressed device, its trusted device identity. Private
   forms, OAuth/file continuations and microphone consent remain on that device.
   Secrets are not copied into prompts or chat drafts. A continuation consumes
   the original bounded approval and rechecks current authority. Completion
   uncertainty is observed through command status instead of automatic replay.
5. **Separate waiting from completion.** `ApplicationExecutionOutcome` accepts
   success only for an explicit committed result. A waiting outcome carries an
   interaction and is not a refusal or completed no-op. Pending, claimed and
   resuming command phases are not execution results. Human-facing synthesis
   and effect accounting retain these distinctions.
6. **Refresh from authenticated source queries.** Addressed state-change hints
   carry command/account identity, affected resources, field names and observation
   time, without new setting values or administrator data. The frontend validates
   the versioned hint and refreshes the relevant owned resources. Receipts and
   existing setters keep source consent, compare-and-set and side effects intact.

## Consequences

New application capabilities require an explicit operation/schema/authority
contract and source-service integration, not a generic route executor. Sensitive
operations may need a browser continuation and cannot be declared completed from
a tool draft or a opened form. Account permissions can change between preparation
and execution, so the later checks are intentional rather than redundant.

Encrypted persistence protects command payload storage; it does not replace
authorization. Durable identity and fenced claims are not proof of arbitrary
external exactly-once delivery. A lost external result remains uncertain.

## Qualification and limits

The source includes behavioral suites for strict claims, changed/missing approval,
current authority, origin/session binding, schema drift, conflict outcomes,
secure continuations, addressed recording protocol and frontend state refresh.
Their current release results belong to the release qualification report.
This ADR does not infer full provider/device/browser coverage or regulatory
certification from those tests.

- [Operation declarations](../../apps/api/src/domains/agents/application/operation_spec.py)
- [Fresh authority](../../apps/api/src/domains/agents/application/authorization.py)
- [Execution validation](../../apps/api/src/domains/agents/application/command_service.py)
- [Command repository](../../apps/api/src/domains/agents/application/command_repository.py)
- [Outcome contract](../../apps/api/src/domains/agents/application/outcomes.py)
- [Strict claim tests](../../apps/api/tests/unit/domains/agents/application/test_strict_claim_policy.py)
- [Origin binding tests](../../apps/api/tests/unit/domains/agents/application/test_command_origin_binding.py)
