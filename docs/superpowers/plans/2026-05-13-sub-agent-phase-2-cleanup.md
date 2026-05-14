# Sub-Agents Phase 2 Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the dormant F6 "persistent sub-agents" plumbing now that the ephemeral planner-delegation path (ADR-083) no longer depends on it. No user-facing change; the project sheds dead code that no UI consumer reaches.

**Architecture:** Phase 1 (ADR-083) rewired `delegate_to_sub_agent_tool` onto `ReactSubAgentRunner`. After Phase 1, the `sub_agents/executor.py` mini-pipeline (`SubAgentExecutor` + `_analyze_instruction` + `_synthesize_results`) is only reached via the REST API `/sub-agents/{id}/execute` and the `recover_stale_subagents` scheduler job. The frontend never calls `/sub-agents` (only `/auth/me/sub-agents-preference`, the on/off toggle — `SubAgentsSettings.tsx` is itself an orphan component, not rendered anywhere). So the entire persistent-path subsystem is dead code: deletion is safer than migration.

**Tech Stack:** FastAPI router removal, Alembic migration to drop a table + column, frontend component deletion, test cleanup, i18n key removal across 6 locales.

**Spec / context:** [`ADR-083`](../../architecture/ADR-083-Sub-Agent-Delegation-React.md) §"Out of scope" identified this cleanup. The audit confirms zero frontend consumer of `/sub-agents` (only `SubAgentsSettings.tsx` calls `/auth/me/sub-agents-preference`, which itself remains used).

---

## Preconditions (run BEFORE starting any task)

These verifications must succeed before deleting anything. They confirm the persistent path is genuinely dead.

- [ ] **A. Frontend audit — confirm zero `/sub-agents` consumer**
  ```bash
  grep -rn "/sub-agents\b\|/sub-agents/" apps/web/src
  ```
  Expected: only the single line in `SubAgentsSettings.tsx` calling `/auth/me/sub-agents-preference`. No `/sub-agents` (CRUD) hit. If anything else appears, **stop and re-evaluate** — the persistent path is in use somewhere unexpected.

- [ ] **B. Verify `SubAgentsSettings.tsx` is unused**
  ```bash
  grep -rn "SubAgentsSettings" apps/web/src --include="*.tsx" --include="*.ts"
  ```
  Expected: matches only `SubAgentsSettings.tsx` itself (not imported anywhere). If imported in `dashboard/settings/page.tsx` or elsewhere, the component is live and we keep it — only `/sub-agents` CRUD goes.

- [ ] **C. Verify `SubAgentExecutor` consumers**
  ```bash
  grep -rn "SubAgentExecutor\b" apps/api/src/ --include="*.py" | grep -v "__pycache__"
  ```
  Expected: only `sub_agents/executor.py` (definition), `sub_agents/router.py` (REST endpoint), `main.py` (stale-recovery scheduler), and a doc comment in `agents/tools/sub_agent_tools.py`. **No other consumer.** If anything else appears, investigate.

- [ ] **D. Verify `sub_agents` DB table holds nothing in prod**
  ```bash
  ssh -p 2222 jgo@192.168.0.14 "docker exec lia-postgres-prod psql -U lia -d lia -c 'SELECT COUNT(*) FROM sub_agents;'"
  ```
  If the count is 0 or close to 0 (only template-generated ephemerals that should have been cleaned up), proceed. If there's a meaningful number of rows from real user-created sub-agents, escalate — we may want to keep the data and remove only the UI/code, not the table.

- [ ] **E. Verify the chantier branch is healthy in main**
  ```bash
  git log --oneline main | head
  ```
  All ADR-083 checkpoints (A-E) should be merged before this cleanup starts. This plan modifies code that ADR-083 just touched — don't double-edit live branches.

If all five preconditions hold, proceed with Task 1.

---

## Task 1: Remove the `/sub-agents` REST router and CRUD layer

**Files:**
- Delete: `apps/api/src/domains/sub_agents/router.py`
- Delete: `apps/api/src/domains/sub_agents/service.py`
- Delete: `apps/api/src/domains/sub_agents/repository.py`
- Delete: `apps/api/src/domains/sub_agents/schemas.py`
- Modify: `apps/api/src/api/v1/routes.py` — drop the `sub_agents_router` include block.
- Modify: `apps/api/tests/unit/domains/sub_agents/test_service.py` — delete the file (it tests `SubAgentService`).

- [ ] **Step 1: Locate the router include block in `routes.py`**
  ```bash
  grep -n "sub_agents_router\|sub_agents" apps/api/src/api/v1/routes.py
  ```
  Expected: a block guarded by `if getattr(settings, "sub_agents_enabled", False)` (~line 49-52). Note the exact lines.

- [ ] **Step 2: Remove the include block**
  Edit `apps/api/src/api/v1/routes.py`. Delete the `if getattr(settings, "sub_agents_enabled", False):` block that imports and includes `sub_agents_router`.

- [ ] **Step 3: Delete the four files**
  ```bash
  rm apps/api/src/domains/sub_agents/router.py
  rm apps/api/src/domains/sub_agents/service.py
  rm apps/api/src/domains/sub_agents/repository.py
  rm apps/api/src/domains/sub_agents/schemas.py
  rm apps/api/tests/unit/domains/sub_agents/test_service.py
  ```

- [ ] **Step 4: Verify nothing else imports them**
  ```bash
  grep -rn "from src.domains.sub_agents.router\|from src.domains.sub_agents.service\|from src.domains.sub_agents.repository\|from src.domains.sub_agents.schemas" apps/api/src/ apps/api/tests/ | grep -v "__pycache__"
  ```
  Expected: empty. If anything remains, **stop** and trace the import chain.

- [ ] **Step 5: Run the API import-startup check**
  ```bash
  docker restart lia-api-dev
  until docker ps --filter "name=lia-api-dev" --filter "health=healthy" --format "{{.Names}}" | grep -q lia-api-dev; do sleep 3; done
  docker logs lia-api-dev --since 60s | grep -iE "traceback|importerror" | grep -v "telegram_shutdown\|MCP\|n8n\|currency_rate"
  ```
  Expected: container healthy, empty error scan.

- [ ] **Step 6: Run the full unit test suite**
  ```bash
  cd apps/api && .venv/Scripts/pytest tests/unit -q -m unit
  ```
  Expected: all pass. (Tests covering deleted classes are deleted; ephemeral-path tests untouched.)

- [ ] **Step 7: Lint + mypy**
  ```bash
  cd apps/api && .venv/Scripts/ruff check src tests && .venv/Scripts/mypy src
  ```
  Expected: no errors.

- [ ] **Step 8: Commit**
  Conventional commit, e.g.:
  ```
  chore(sub_agents): remove dormant /sub-agents REST router + CRUD layer

  The persistent sub-agent feature (CRUD via /sub-agents, templates, etc.)
  had no UI consumer (audit: zero call from apps/web/src). Now that
  ADR-083 has moved the planner's delegation path off SubAgentExecutor,
  this code is fully dead — deletion is safer than migration.

  - Removed: router.py, service.py, repository.py, schemas.py.
  - Removed: tests/unit/.../test_service.py.
  - Removed: sub_agents_router include in api/v1/routes.py.

  SubAgentExecutor still exists at this point — see Task 2 for its
  removal alongside the stale-recovery scheduler job.
  ```

---

## Task 2: Remove `SubAgentExecutor`, its prompt and constants, and the stale-recovery scheduler job

**Files:**
- Delete: `apps/api/src/domains/sub_agents/executor.py`
- Delete: `apps/api/src/domains/sub_agents/token_guard.py` (dormant, never wired)
- Delete: `apps/api/src/domains/agents/prompts/v1/subagent_synthesis_prompt.txt`
- Delete: `apps/api/tests/unit/domains/sub_agents/test_executor.py`
- Modify: `apps/api/src/domains/sub_agents/constants.py` — remove `SUBAGENT_SYNTHESIS_PROMPT_NAME`, `SUBAGENT_EXCLUDED_PLANNER_TOOLS`, `SUBAGENT_DAILY_BUDGET_KEY_PREFIX`, `SUBAGENT_DAILY_BUDGET_TTL_SECONDS`, `SUBAGENT_TEMPLATES`, `get_template_by_id`. Keep `SUBAGENT_DEFAULT_BLOCKED_TOOLS`, `SUBAGENT_READ_ONLY_PREFIX`, `SUBAGENT_CONTEXT_SUMMARY_PREFIX` (used by the ephemeral path's `resolve_tools_for_subagent` / `build_subagent_system_prompt`).
- Modify: `apps/api/src/domains/sub_agents/skill_resolver.py` — drop `build_subagent_system_prompt` and `resolve_skills_context` (only used by `SubAgentExecutor`). Keep `resolve_tools_for_subagent` and `is_skill_visible_to_agent` (still used).
- Modify: `apps/api/src/domains/agents/prompts/prompt_loader.py` — remove `"subagent_synthesis_prompt"` from the `PromptName` Literal.
- Modify: `apps/api/src/main.py` — remove the stale-recovery scheduler job registration block (`SubAgentExecutor.recover_stale_subagents` registration at line ~843).
- Modify: `apps/api/src/core/constants.py` — remove `SCHEDULER_JOB_SUBAGENT_STALE_RECOVERY`, `SUBAGENT_MAX_PER_USER_DEFAULT`, `SUBAGENT_MAX_CONCURRENT_DEFAULT`, `SUBAGENT_MAX_DEPTH_DEFAULT`, `SUBAGENT_DEFAULT_TIMEOUT_DEFAULT`, `SUBAGENT_MAX_TOKEN_BUDGET_DEFAULT`, `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY_DEFAULT`, `SUBAGENT_MAX_CONSECUTIVE_FAILURES_DEFAULT`, `SUBAGENT_STALE_RECOVERY_INTERVAL_DEFAULT`. Keep `TOOL_NAME_DELEGATE_SUB_AGENT`, `SUB_AGENTS_ENABLED_DEFAULT`, `SUBAGENT_DEFAULT_MAX_ITERATIONS_DEFAULT` (reused by `recursion_limit`), `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED_DEFAULT`, `SUBAGENT_VETO_POINTLESS_ENABLED_DEFAULT`.
- Modify: `apps/api/src/core/config/agents.py` — remove the corresponding Settings fields (`subagent_max_per_user`, `subagent_max_concurrent`, `subagent_max_depth`, `subagent_default_timeout`, `subagent_max_token_budget`, `subagent_max_total_tokens_per_day`, `subagent_max_consecutive_failures`, `subagent_stale_recovery_interval_seconds`) and their imports. Keep `subagent_default_max_iterations`, `subagent_instruction_max_tokens_resolved`, `subagent_veto_pointless_enabled`, `sub_agents_enabled`.
- Modify: `.env.example` and `.env.prod.example` — remove the obsolete env var lines (matching the removed Settings fields).
- Modify: `apps/api/tests/unit/domains/sub_agents/test_constants.py` — remove assertions about deleted constants (`SUBAGENT_TEMPLATES`, etc.).

- [ ] **Step 1: Snapshot current test count for regression baseline**
  ```bash
  cd apps/api && .venv/Scripts/pytest tests/unit -q -m unit --co 2>&1 | tail -1
  ```
  Note the test count.

- [ ] **Step 2: Delete `executor.py`, `token_guard.py`, the synthesis prompt, and the executor test**
  ```bash
  rm apps/api/src/domains/sub_agents/executor.py
  rm apps/api/src/domains/sub_agents/token_guard.py
  rm apps/api/src/domains/agents/prompts/v1/subagent_synthesis_prompt.txt
  rm apps/api/tests/unit/domains/sub_agents/test_executor.py
  ```

- [ ] **Step 3: Prune `sub_agents/constants.py`**
  Open the file. Delete the `SUBAGENT_DAILY_BUDGET_*`, `SUBAGENT_EXCLUDED_PLANNER_TOOLS`, `SUBAGENT_SYNTHESIS_PROMPT_NAME`, `SUBAGENT_TEMPLATES`, and `get_template_by_id` definitions. Keep `SUBAGENT_DEFAULT_BLOCKED_TOOLS`, `SUBAGENT_READ_ONLY_PREFIX`, `SUBAGENT_CONTEXT_SUMMARY_PREFIX`.

- [ ] **Step 4: Prune `sub_agents/skill_resolver.py`**
  Open the file. Delete `build_subagent_system_prompt` and `resolve_skills_context`. Keep `resolve_tools_for_subagent` and `is_skill_visible_to_agent`. Also remove imports of `SUBAGENT_CONTEXT_SUMMARY_PREFIX` and `SUBAGENT_READ_ONLY_PREFIX` if no longer referenced.

- [ ] **Step 5: Prune `prompt_loader.py`**
  Open `apps/api/src/domains/agents/prompts/prompt_loader.py`. In the `PromptName = Literal[...]` block, remove the line `"subagent_synthesis_prompt",`.

- [ ] **Step 6: Remove the stale-recovery job registration in `main.py`**
  Locate the block around line 843 that imports `SubAgentExecutor` and registers `SubAgentExecutor.recover_stale_subagents` as a scheduler job. Delete it entirely (including the surrounding feature-flag check, if any).

- [ ] **Step 7: Prune `core/constants.py` and `core/config/agents.py`**
  Remove the unused `SUBAGENT_*` defaults and the corresponding Pydantic fields per the file list above. Preserve the ADR-083 fields and `subagent_default_max_iterations` / `sub_agents_enabled`.

- [ ] **Step 8: Prune `.env.example` and `.env.prod.example`**
  Remove env var lines for the deleted settings:
  - `SUBAGENT_MAX_PER_USER`, `SUBAGENT_MAX_CONCURRENT`, `SUBAGENT_DEFAULT_TIMEOUT`, `SUBAGENT_MAX_TOKEN_BUDGET`, `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY`, `SUBAGENT_MAX_CONSECUTIVE_FAILURES`, `SUBAGENT_STALE_RECOVERY_INTERVAL_SECONDS`, `SUBAGENT_MAX_DEPTH`.
  Preserve: `SUB_AGENTS_ENABLED`, `SUBAGENT_DEFAULT_MAX_ITERATIONS`, `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`, `SUBAGENT_VETO_POINTLESS_ENABLED`.

- [ ] **Step 9: Adapt `test_constants.py`**
  Open `apps/api/tests/unit/domains/sub_agents/test_constants.py`. Remove assertions that reference deleted constants (`SUBAGENT_TEMPLATES`, `SUBAGENT_SYNTHESIS_PROMPT_NAME`, etc.). Keep assertions on `SUBAGENT_DEFAULT_BLOCKED_TOOLS`, `SUBAGENT_READ_ONLY_PREFIX` if any.

- [ ] **Step 10: Verify nothing imports the deleted symbols**
  ```bash
  grep -rn "SubAgentExecutor\|SubAgentTokenGuard\|build_subagent_system_prompt\|resolve_skills_context\|SUBAGENT_TEMPLATES\|SUBAGENT_SYNTHESIS_PROMPT_NAME\|SUBAGENT_EXCLUDED_PLANNER_TOOLS\|SUBAGENT_DAILY_BUDGET\|subagent_synthesis_prompt" apps/api/src apps/api/tests | grep -v "__pycache__"
  ```
  Expected: empty.

- [ ] **Step 11: Docker dev import-startup check**
  ```bash
  docker restart lia-api-dev
  until docker ps --filter "name=lia-api-dev" --filter "health=healthy" --format "{{.Names}}" | grep -q lia-api-dev; do sleep 3; done
  docker logs lia-api-dev --since 60s | grep -iE "traceback|importerror|attributeerror" | grep -v "telegram_shutdown\|MCP\|n8n\|currency_rate"
  ```
  Expected: container healthy, empty error scan.

- [ ] **Step 12: Run the full unit test suite + lint + mypy**
  ```bash
  cd apps/api && .venv/Scripts/pytest tests/unit -q -m unit && .venv/Scripts/ruff check src tests && .venv/Scripts/mypy src
  ```
  Expected: all pass.

- [ ] **Step 13: Commit**
  ```
  chore(sub_agents): remove SubAgentExecutor + bespoke pipeline (dead code post-ADR-083)

  After Task 1, SubAgentExecutor was only reached by the (deleted) /sub-agents
  REST router and the stale-recovery scheduler job. The ephemeral planner-
  delegation path runs on ReactSubAgentRunner. Drop the executor, its
  dormant token guard, the synthesis prompt, the stale-recovery job, and
  the now-unused Pydantic settings + env vars.

  Kept (still used by the ephemeral path): SUBAGENT_DEFAULT_BLOCKED_TOOLS,
  resolve_tools_for_subagent, SUB_AGENTS_ENABLED, SUBAGENT_DEFAULT_MAX_ITERATIONS,
  SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED, SUBAGENT_VETO_POINTLESS_ENABLED.
  ```

---

## Task 3: Drop the `sub_agents` DB table + `parent_run_id` column

**Files:**
- Create: `apps/api/alembic/versions/2026_05_13_XXXX_drop_sub_agents_table.py`
- Modify: `apps/api/src/domains/sub_agents/models.py` — delete the `SubAgent` ORM model + enums (`SubAgentStatus`, `SubAgentCreatedBy`). Keep `__init__.py` exports clean.
- Modify: `apps/api/src/domains/sub_agents/__init__.py` — remove exports of `SubAgent`, `SubAgentStatus`, `SubAgentCreatedBy` if present.
- Modify: `apps/api/src/infrastructure/database/registry.py` — remove `import src.domains.sub_agents.models` (the model registration line).
- Modify: `apps/api/src/main.py` — remove the equivalent registration import in the lifespan.
- Modify: `apps/api/tests/conftest.py` — remove `import src.domains.sub_agents.models` if it's there for mapper registration.

- [ ] **Step 1: Snapshot the table schema and any existing rows**
  Before dropping, capture state (safety / future audit):
  ```bash
  ssh -p 2222 jgo@192.168.0.14 "docker exec lia-postgres-prod pg_dump -U lia -d lia -t sub_agents --schema-only" > docs/architecture/_archive/sub_agents_schema_2026-05-13.sql
  ssh -p 2222 jgo@192.168.0.14 "docker exec lia-postgres-prod pg_dump -U lia -d lia -t sub_agents --data-only" > docs/architecture/_archive/sub_agents_data_2026-05-13.sql
  ```
  Keep these archived SQL files (or copy out, don't commit binary db dumps to repo if the dir already has policies).

- [ ] **Step 2: Generate the Alembic migration**
  ```bash
  cd apps/api && task db:migrate:create -- "drop sub_agents table and parent_run_id column"
  ```
  Edit the generated migration:

  ```python
  """drop sub_agents table and parent_run_id column

  Revision ID: <auto>
  Revises: <previous_revision>
  Create Date: 2026-05-13

  ADR-083 Phase 2 cleanup. The /sub-agents REST API + SubAgentExecutor were
  removed (no frontend consumer). The sub_agents table held only ephemerals
  cleaned up at the end of each delegate_to_sub_agent_tool call (now obsolete
  too — the ephemeral path doesn't create ORM records).

  parent_run_id was added (2026_03_16_0002) for hierarchical token queries
  but was never populated — drop it.
  """
  from alembic import op
  import sqlalchemy as sa

  revision = "..."
  down_revision = "..."

  def upgrade() -> None:
      # Drop foreign-key-bearing table first
      op.drop_index("ix_sub_agents_enabled", table_name="sub_agents")
      op.drop_index("ix_sub_agents_user_name", table_name="sub_agents")
      op.drop_index("ix_sub_agents_user_id", table_name="sub_agents")
      op.drop_table("sub_agents")
      # Drop the now-unused column
      op.drop_column("message_token_summary", "parent_run_id")

  def downgrade() -> None:
      # Recreate parent_run_id (nullable, no FK — was a hint column).
      op.add_column(
          "message_token_summary",
          sa.Column("parent_run_id", sa.String(length=64), nullable=True),
      )
      # Recreate sub_agents table — minimal columns to restore round-trip.
      # If a real rollback is ever needed, restore data from the archived
      # SQL dump (docs/architecture/_archive/sub_agents_*.sql).
      op.create_table(
          "sub_agents",
          sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
          sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
          sa.Column("name", sa.String(length=100), nullable=False),
          sa.Column("description", sa.String(length=500)),
          sa.Column("system_prompt", sa.Text()),
          sa.Column("status", sa.String(length=20)),
          sa.Column("created_by", sa.String(length=20)),
          sa.Column("is_enabled", sa.Boolean(), default=True),
          sa.Column("created_at", sa.DateTime(timezone=True)),
          sa.Column("updated_at", sa.DateTime(timezone=True)),
          # ... (minimal — restore from archive for a real rollback)
      )
      op.create_index("ix_sub_agents_user_id", "sub_agents", ["user_id"])
      op.create_index("ix_sub_agents_user_name", "sub_agents", ["user_id", "name"], unique=True)
      op.create_index("ix_sub_agents_enabled", "sub_agents", ["is_enabled"], postgresql_where=sa.text("is_enabled = true"))
  ```

- [ ] **Step 3: Delete `sub_agents/models.py` + adjust `__init__.py`**
  ```bash
  rm apps/api/src/domains/sub_agents/models.py
  ```
  Edit `apps/api/src/domains/sub_agents/__init__.py` (and `apps/api/src/infrastructure/database/registry.py`, `main.py`, `conftest.py`) to drop the import of `sub_agents.models`.

- [ ] **Step 4: Apply migration in dev DB**
  ```bash
  task db:migrate
  ```
  Expected: `sub_agents` table dropped, `message_token_summary.parent_run_id` removed.

- [ ] **Step 5: Smoke test — fresh API + DB starts clean**
  ```bash
  docker restart lia-api-dev
  until docker ps --filter "name=lia-api-dev" --filter "health=healthy" --format "{{.Names}}" | grep -q lia-api-dev; do sleep 3; done
  docker logs lia-api-dev --since 60s | grep -iE "traceback|importerror|attributeerror|InvalidRequestError" | grep -v "telegram_shutdown\|MCP\|n8n\|currency_rate"
  ```
  Expected: container healthy, no SQLAlchemy mapper errors.

- [ ] **Step 6: Full test suite**
  ```bash
  cd apps/api && .venv/Scripts/pytest tests/unit tests/integration -q
  ```
  Expected: all pass. (Any test that imported `SubAgent` ORM has already been deleted in Tasks 1-2; if anything still references it, **stop** and trace.)

- [ ] **Step 7: Commit**
  ```
  chore(sub_agents): drop sub_agents table + parent_run_id column

  ADR-083 Phase 2 cleanup. Alembic migration drops the dead table and the
  never-populated parent_run_id column on message_token_summary. SubAgent
  ORM model + status/created_by enums deleted; mapper registration removed
  from registry, main lifespan, and conftest.

  Schema + data archived under docs/architecture/_archive/sub_agents_*.sql
  for forensic / disaster-recovery purposes.
  ```

---

## Task 4: Remove the orphan `SubAgentsSettings.tsx` and the `/auth/me/sub-agents-preference` endpoint, OR keep them as the user-facing toggle

This is a **product decision**, not a technical one. Two options:

**Option A — Keep the toggle, drop only the orphan component**:
- The endpoint `/auth/me/sub-agents-preference` and the `users.sub_agents_enabled` column stay (consumed by `delegate_to_sub_agent_tool`'s preference check in `sub_agent_tools.py`).
- The frontend `SubAgentsSettings.tsx` is rendered somewhere in Settings (currently it isn't — needs wiring). Then the user can actually disable delegation from the UI.

**Option B — Drop both as well**:
- Remove `SubAgentsSettings.tsx`, the endpoint, the `users.sub_agents_enabled` column (with migration), and the preference check in `sub_agent_tools.py`. Result: the planner ALWAYS sees `delegate_to_sub_agent_tool` available (subject to `SUB_AGENTS_ENABLED` global flag).

**Recommendation**: **Option A**, but wire the component into `dashboard/settings/page.tsx`. The user-level opt-out is cheap, useful, and the only piece of "persistent sub-agents" that was actually completable. If wiring it is out of scope of this cleanup, defer to a separate task and **don't delete the endpoint or the column yet**.

- [ ] **Step 1: Decide A or B with the user** (this requires a product call, not a code edit).
- [ ] **Step 2 (Option A)**: Wire `SubAgentsSettings` into `apps/web/src/app/[lng]/dashboard/settings/page.tsx` alongside the other settings sections (`UserDebugSettings`, `VoiceModeSettings`, etc.). Verify in Docker dev that the toggle appears and works.
- [ ] **Step 2 (Option B)**: Delete the component, the endpoint, the column (with migration), and the preference check. Update i18n keys (`sub_agents.settings.*`) across 6 locales.

---

## Task 5: Strip i18n keys related to deleted features

**Files:**
- Modify: `apps/web/locales/{en,fr,de,es,it,zh}/translation.json`

Keys to remove (only after Task 4 is complete and we know if the toggle survives):

- `sub_agents.templates.research_assistant.*` and the other two templates (`writing_assistant`, `data_analyst`) — the templates are deleted.
- `sub_agents.settings.*` if Option B is chosen in Task 4.

Keep:
- `settings.admin.llmConfig.types.subagent` (renamed in ADR-083 Task 8).
- Any `sub_agents` keys still referenced by surviving code.

- [ ] **Step 1: Identify keys to remove**
  ```bash
  cd apps/web/locales && grep -nE "sub_agents\.(templates|settings)" en/translation.json
  ```

- [ ] **Step 2: Remove the keys from all 6 locales atomically (so pre-commit parity check passes)**
  For each locale, delete the same set of keys. Use a small script if the count is large:
  ```bash
  python -c "
  import json
  from pathlib import Path
  for lang in ['en','fr','de','es','it','zh']:
      p = Path(f'apps/web/locales/{lang}/translation.json')
      data = json.loads(p.read_text(encoding='utf-8'))
      # Drop dead keys
      data['sub_agents'].pop('templates', None)
      # if Option B: data['sub_agents'].pop('settings', None)
      # Clean up empty sub_agents block if it becomes empty
      if 'sub_agents' in data and not data['sub_agents']:
          data.pop('sub_agents')
      p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
  "
  ```

- [ ] **Step 3: Run the i18n parity check (replicates the pre-commit hook)**
  ```bash
  python -c "
  import json
  from pathlib import Path
  base = Path('apps/web/locales')
  def collect(o, p=''):
      if isinstance(o, dict):
          out = set()
          for k, v in o.items():
              path = f'{p}.{k}' if p else k
              out.add(path); out.update(collect(v, path))
          return out
      return set()
  ref = collect(json.loads((base/'en'/'translation.json').read_text(encoding='utf-8')))
  for l in ['fr','de','es','it','zh']:
      keys = collect(json.loads((base/l/'translation.json').read_text(encoding='utf-8')))
      assert keys == ref, f'{l} drifted: missing={ref-keys}, extra={keys-ref}'
  print('OK')
  "
  ```
  Expected: `OK`.

- [ ] **Step 4: Frontend tsc + eslint**
  ```bash
  cd apps/web && pnpm tsc --noEmit && pnpm lint
  ```
  Expected: no errors. (Run via Docker dev container if local rule forbids — adapt to project convention.)

- [ ] **Step 5: Commit**
  ```
  chore(i18n): drop dead sub_agents.templates keys (Phase 2 cleanup)

  Templates (research_assistant, writing_assistant, data_analyst) were
  removed in Task 2 — their i18n keys can no longer be referenced.
  Parity preserved across all 6 locales.
  ```

---

## Final validation (after all tasks)

- [ ] **Full pre-commit check**
  ```bash
  task pre-commit
  ```
  Expected: format + lint + fast unit tests + i18n parity + frontend tsc all pass.

- [ ] **End-to-end smoke in Docker dev**
  Run the incident query "résume mes 5 derniers emails de ma femme" and a multi-domain expert query that legitimately delegates. Confirm: token totals identical to post-ADR-083 baselines (~16K and ~17K respectively), no `subagent` ORM activity (no `sub_agents` table queries in PG logs), the « Sub-Agent (ReAct) » entry in the admin LLM panel is unchanged.

- [ ] **Update ADR-083 § "Out of scope" → "Completed in Phase 2 cleanup"**
  Edit `docs/architecture/ADR-083-Sub-Agent-Delegation-React.md`, move the "Persistent sub-agent migration" bullet from "Negative / accepted" to a new "Phase 2 completion note (2026-XX-XX)" subsection. Reference the commits/PR.

- [ ] **Update `docs/technical/SUB_AGENTS.md`**
  Rewrite to reflect a single execution path (ReAct via `ReactSubAgentRunner`). Remove the "Database Schema", "API Endpoints", "Templates" sections. Keep the "Planner Integration", "Token Tracking", "2026-05-13 Redesign (ADR-083)" sections (trim mentions of the now-deleted persistent path).

---

## Risk assessment

| Risk | Likelihood | Mitigation |
|---|---|---|
| Hidden import in a forgotten module crashes startup | Low | Step 4 of every task has an explicit `grep` for residual imports + Docker restart + error scan. Stop if anything appears. |
| Migration downgrade is incomplete (Task 3) | Medium | Schema + data dumped to `_archive/` before drop. Downgrade SQL provided in the migration; a real rollback would restore from the archived dump. Accepted trade-off — the table holds no meaningful data. |
| `sub_agents_enabled` user preference check breaks when column is dropped (Option B of Task 4) | Medium | Option A is recommended precisely to avoid this. If Option B is chosen, the preference check in `sub_agent_tools.py` must be removed in the same commit as the column drop. |
| A prod user's `sub_agents` table actually contains real rows from the (orphan) UI somehow | Low (UI never rendered) | Precondition D verifies this. Stop and reassess if non-zero. |

## What we are NOT removing

- `apps/api/src/domains/agents/tools/sub_agent_tools.py` (`delegate_to_sub_agent_tool`) — the ephemeral path, the whole point of ADR-083.
- `apps/api/src/domains/agents/prompts/v1/subagent_react_prompt.txt` — new prompt for the ReAct sub-agent.
- `apps/api/src/domains/sub_agents/skill_resolver.py::resolve_tools_for_subagent` + `is_skill_visible_to_agent` — still used by the ephemeral path.
- `SUBAGENT_DEFAULT_BLOCKED_TOOLS`, `SUB_AGENTS_ENABLED`, `SUBAGENT_DEFAULT_MAX_ITERATIONS`, `SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED`, `SUBAGENT_VETO_POINTLESS_ENABLED` — settings + constants still consumed by the ephemeral path.
- `delegate_to_sub_agent_catalogue_manifest` — the tool's catalogue entry.
- `apps/api/src/domains/agents/orchestration/semantic_validator.py::validate_sub_agent_delegation_justified` — the H1 veto.
- LLM type `"subagent"` in `LLM_TYPES_REGISTRY` — the model selector for the ReAct sub-agent.
