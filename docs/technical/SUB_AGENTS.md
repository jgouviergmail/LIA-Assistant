# Sub-Agents — Technical Documentation

## Overview

Sub-agents are persistent, specialized assistants that the principal LIA agent can delegate tasks to. They execute through a **simplified direct pipeline** (query analysis → planner → parallel executor → LLM synthesis), bypassing the full graph's semantic validator, approval gate, and response node. Domain detection uses the same `analyze_query()` LLM call as the main assistant's router. Tools are restricted to read-only in V1.

Sub-agents are **invisible to the user** — the principal assistant orchestrates them and presents results through natural conversation messages.

## Architecture

### Domain Structure (DDD)

```
src/domains/sub_agents/
├── __init__.py          # Public exports
├── models.py            # SubAgent ORM model, SubAgentStatus, SubAgentCreatedBy enums
├── repository.py        # SubAgentRepository(BaseRepository[SubAgent])
├── schemas.py           # Pydantic v2 request/response schemas
├── service.py           # SubAgentService — CRUD, templates, execution recording
├── router.py            # FastAPI REST endpoints (/sub-agents)
├── constants.py         # Settings defaults, blocked tools, templates, read-only prefix
├── executor.py          # (Phase B) SubAgentExecutor — sync/background execution
├── skill_resolver.py    # (Phase B) Skills and tools resolution for sub-agents
└── token_guard.py       # (Phase B) Mid-execution token budget monitoring
```

### Database Schema

**Table: `sub_agents`**

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | UUID | FK → users.id (CASCADE) |
| name | String(100) | Unique per user |
| description | String(500) | Specialization description |
| system_prompt | Text | Custom instructions |
| llm_provider | String(50) | Override provider (null = inherit) |
| llm_model | String(100) | Override model (null = inherit) |
| llm_temperature | Float | Override temperature (null = inherit) |
| max_iterations | Integer | Recursion limit (1-15, default 5) |
| timeout_seconds | Integer | Hard timeout (10-600, default 120) |
| skill_ids | JSONB | Skills assigned to this sub-agent |
| allowed_tools | JSONB | Tool whitelist (empty = all except blocked) |
| blocked_tools | JSONB | Tool blacklist (V1: all write tools) |
| is_enabled | Boolean | Enable/disable toggle |
| status | String(20) | ready / executing / error |
| created_by | String(20) | user / assistant |
| template_id | String(50) | Template source (tracking) |
| execution_count | Integer | Total executions |
| consecutive_failures | Integer | Auto-disable threshold |
| last_execution_summary | Text | Injected as context in next run |

**Indexes:**
- `ix_sub_agents_user_id` — User lookup
- `ix_sub_agents_user_name` — Unique (user_id, name)
- `ix_sub_agents_enabled` — Partial index (is_enabled = true)

### API Endpoints

All endpoints require authentication (`get_current_active_session`).

| Method | Path | Description |
|--------|------|-------------|
| GET | `/sub-agents` | List all sub-agents for user |
| GET | `/sub-agents/templates` | List available templates |
| POST | `/sub-agents` | Create a sub-agent |
| POST | `/sub-agents/from-template/{template_id}` | Create from template |
| GET | `/sub-agents/{id}` | Get sub-agent by ID |
| PATCH | `/sub-agents/{id}` | Partial update |
| DELETE | `/sub-agents/{id}` | Delete (hard) |
| PATCH | `/sub-agents/{id}/toggle` | Toggle is_enabled |
| POST | `/sub-agents/{id}/execute` | Execute (Phase B) |
| DELETE | `/sub-agents/{id}/execution` | Kill execution (Phase B) |

### Planner Integration

Single transversal tool: `delegate_to_sub_agent_tool` — always in the planner catalogue.

| Tool | Parameters | Description |
|------|-----------|-------------|
| `delegate_to_sub_agent_tool` | `expertise`, `instruction` | Creates an ephemeral expert sub-agent and executes it |

**How it works:**
1. The planner sees the tool in **every** filtered catalogue (force-included via `NormalFilteringStrategy`)
2. The planner prompt contains a `{sub_agents_section}` with guidelines on when to delegate
3. The planner decides autonomously to delegate (complex analysis, parallel research, domain expertise)
4. Multiple delegates with no `depends_on` → **parallel execution** (wave-based)
5. Results referenced via `$steps.step_N.analysis` for chaining

**Depth limit:** Sub-agents cannot spawn sub-sub-agents (session_id prefix `subagent_` check).

**Catalogue manifest:** `src/domains/agents/sub_agents/catalogue_manifests.py` (AgentManifest + ToolManifest with semantic_keywords for natural discovery).

### Configuration

Feature flag: `SUB_AGENTS_ENABLED=false` (disabled by default).

All settings are in `src/core/config/agents.py` and documented in `.env.example`.

| Setting | Default | Description |
|---------|---------|-------------|
| `SUB_AGENTS_ENABLED` | false | Feature flag |
| `SUBAGENT_MAX_PER_USER` | 10 | Max sub-agents per user |
| `SUBAGENT_MAX_CONCURRENT` | 3 | Max concurrent executions per user |
| `SUBAGENT_DEFAULT_TIMEOUT` | 120 | Default timeout (seconds) |
| `SUBAGENT_DEFAULT_MAX_ITERATIONS` | 5 | Default max LLM iterations |
| LLM Model | gpt-5.2 | Configured via Admin > LLM Configuration > Sub-Agent |
| `SUBAGENT_MAX_TOKEN_BUDGET` | 50000 | Max tokens per execution |
| `SUBAGENT_MAX_TOTAL_TOKENS_PER_DAY` | 500000 | Daily budget per user |
| `SUBAGENT_MAX_CONSECUTIVE_FAILURES` | 3 | Auto-disable threshold |
| `SUBAGENT_STALE_RECOVERY_INTERVAL_SECONDS` | 120 | Stale recovery job interval |

### Templates

Pre-defined templates in `constants.py` (no DB table):

| ID | Name | Icon | Specialization |
|----|------|------|----------------|
| `research_assistant` | Research Assistant | 🔍 | Web research, multi-source synthesis |
| `writing_assistant` | Writing Assistant | ✍️ | Drafting, editing, content improvement |
| `data_analyst` | Data Analyst | 📊 | Email/calendar/file data analysis |

All templates include `default_blocked_tools` (all write/destructive operations).

### User Preference (Phase D)

Per-user toggle `sub_agents_enabled` (default: `true`, opt-out):
- **Backend**: `users.sub_agents_enabled` column (Boolean, migration `sub_agents_003`)
- **Endpoint**: `PATCH /auth/me/sub-agents-preference` (same pattern as voice_mode/debug_panel)
- **Frontend**: Toggle in Settings > Features > Sub-Agents (`SubAgentsSettings.tsx`)
- **Tool enforcement**: `delegate_to_sub_agent_tool` checks user preference before execution. Returns `FEATURE_DISABLED` error if disabled.

### V1 Constraints

- **Read-only**: Sub-agents cannot perform write operations (blocked_tools enforced)
- **Max depth 1**: Sub-agents cannot spawn other sub-agents
- **Auto-approve**: All plans are auto-approved (no HITL in sub-agents)
- **User preference**: Users can disable sub-agents in their preferences

### V1 Known Limitations (documented trade-offs)

1. **Token guard Level 2 not wired**: `SubAgentTokenGuard` exists (file + tests) but is not integrated in the executor. The `TrackingContext` is created in the executor and passed via `RunnableConfig.callbacks`. V2 will integrate the guard callback. Active guards in V1: timeout + manual cancel.

2. **Token consolidation via parent tracker**: Sub-agent tokens are tracked in a separate `MessageTokenSummary` with sub-agent `session_id`. The tool (`delegate_to_sub_agent_tool`) consolidates them into the parent tracker. The `parent_run_id` column exists (migration) but is not yet populated for hierarchical queries.

3. **No pessimistic lock on status transition**: Two simultaneous requests could pass `_validate_can_execute()` before either flushes EXECUTING status. Theoretical race condition, unlikely in practice (single user, sequential UI). Stale recovery handles zombie cases. V2 will add `SELECT ... FOR UPDATE`.

4. **Redundant status writes**: Executor sets status (READY/ERROR), then `record_execution()` re-sets it. Harmless (record_execution handles auto-disable logic and is the source of truth).

### Token Tracking

- **Sync mode**: Executor creates its own `TrackingContext` with `auto_commit=True` and attaches a `TokenTrackingCallback` to the `RunnableConfig`. All LLM calls (planner + tools + synthesis) propagate tokens through this callback. Tokens tracked in separate `MessageTokenSummary` with sub-agent `session_id`. The parent tool consolidates totals via `parent_tracker.record_node_tokens()`.
- **Background mode**: Standalone `TrackingContext` in background worker. Same pipeline.
- `MessageTokenSummary.parent_run_id` enables future hierarchical cost queries (not populated in V1).

### Skills Visibility (Phase B)

Skills declare their audience via `agent-visibility` in SKILL.md frontmatter:
```yaml
agent-visibility:
  - research_assistant
visibility-mode: include
```

### HITL Rejection Fallback

When a user rejects a plan containing `delegate_to_sub_agent_tool` steps at the approval gate,
the system automatically converts the REJECT into a REPLAN without sub-agents:

1. **Detection**: `approval_gate_node` checks if the rejected plan has sub-agent delegation steps
2. **Conversion**: Sets `needs_replan=True` + `exclude_sub_agent_tools=True` in state
3. **Catalogue exclusion**: `planner_node_v3` passes `exclude_tools` to `SmartPlannerService.plan()`,
   which post-filters `delegate_to_sub_agent_tool` from the catalogue (normal + panic mode)
4. **Cleanup**: Planner clears both flags after generating the new plan (single replan cycle)
5. **Result**: User gets a new plan using direct tools (web_search, etc.) instead of sub-agents

Metric tracked: `hitl_plan_decisions{decision="REPLAN_SUB_AGENT_FALLBACK"}`.

### Semantic Validator Exception

The `for_each` cardinality check (Check 1 in `validate_for_each_patterns`) exempts plans with
2+ explicit `delegate_to_sub_agent_tool` steps — each step delegates to a different expert,
satisfying the "each" cardinality without `for_each` iteration.

Check 5 (repeated tool consolidation) also exempts `delegate_to_sub_agent_tool` since
explicit delegation to different experts cannot be consolidated into a `for_each` pattern.

## Migrations

- `2026_03_16_0001`: Create `sub_agents` table + indexes
- `2026_03_16_0002`: Add `parent_run_id` to `message_token_summary`
