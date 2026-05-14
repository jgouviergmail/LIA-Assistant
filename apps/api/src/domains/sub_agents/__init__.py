"""Sub-Agents domain (post-ADR-083 Phase 2 cleanup).

The domain now provides only what the ephemeral planner-delegation path
(`delegate_to_sub_agent_tool` → `ReactSubAgentRunner`) actually needs:

- `resolve_tools_for_subagent` and `is_skill_visible_to_agent` in
  `skill_resolver.py` — read-only tool filtering for the ReAct sub-agent loop.
- `SUBAGENT_DEFAULT_BLOCKED_TOOLS` in `constants.py` — the read-only blocklist.

The bespoke `SubAgentExecutor` / `SubAgentService` / `SubAgentRepository` /
`SubAgentTokenGuard` and the `/sub-agents` REST API were removed (no UI
consumer; the ephemeral path no longer depends on them). The `sub_agents`
DB table is dropped by migration `phase_2_cleanup_001`, and the per-user
`sub_agents_enabled` preference column was removed (Option B) — delegation
is gated only by the global `SUB_AGENTS_ENABLED` flag now.

See ADR-083 and `docs/superpowers/plans/2026-05-13-sub-agent-phase-2-cleanup.md`.
"""

__all__: list[str] = []
