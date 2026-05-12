-- LLM Configuration Seed Data
-- Generated: 2026-04-09
-- Updated: 2026-05-06 (reasoning_effort overhaul: JSONB conversion, broken combos cleaned)
-- Source: Development database (admin-configured optimal settings)
--
-- Applied on first deployment (APPLY_SEEDS=true or personalities table empty)
-- Uses INSERT ... ON CONFLICT to safely merge with existing config
--
-- ============================================================================
-- reasoning_effort JSONB convention
-- ============================================================================
-- Per the reasoning_effort overhaul, this column is now JSONB. Conventions:
--   - {"effort":"<value>"}      → enum widget (OpenAI gpt-5/o-series, Anthropic
--                                  4.5+, Gemini 3.x, DeepSeek V4, Perplexity
--                                  deep-research). Value must be in the model's
--                                  reasoning_enum_values matrix.
--   - {"enabled":false}         → toggle off (Qwen 'none' / DeepSeek V4 'off').
--   - {"enabled":true,...}      → toggle on (Qwen with optional budget).
--   - {"budget":<int>}          → Gemini 2.5 thinking budget (0..32768, plus
--                                  sentinels 0=off, -1=dynamic).
--   - NULL                      → no override (model default applies, OR the
--                                  model is non-reasoning and the value would
--                                  be silently ignored anyway).
-- Broken combos (non-reasoning model + reasoning_effort) have been set to NULL.
-- Rows referencing 25 deleted models (claude-sonnet-4-6 retired etc.) have
-- been removed.

-- ============================================================================
-- LLM CONFIG OVERRIDES
-- ============================================================================
-- Strategy:
--   - Domain agents (contacts, emails, calendar, etc.): gpt-4.1-nano (fast, cheap)
--   - Routing/analysis (router, query_analyzer, semantic): gpt-4.1-mini (balanced)
--   - Planning (planner): qwen3.5-plus (cost-effective reasoning)
--   - Advanced (browser, subagent, mcp_react): gpt-5.4 (full capability)

INSERT INTO llm_config_overrides (id, llm_type, provider, model, temperature, max_tokens, reasoning_effort, created_at, updated_at)
VALUES
    -- Domain agents (fast, cheap — gpt-4.1-nano, non-reasoning, no effort)
    (gen_random_uuid(), 'brave_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'calendar_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'contacts_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'drive_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'emails_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hue_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'perplexity_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'places_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'routes_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'tasks_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'weather_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'web_fetch_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'web_search_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'wikipedia_agent', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),

    -- Routing & analysis (balanced — gpt-4.1-mini = non-reasoning, gpt-5-mini = reasoning)
    (gen_random_uuid(), 'broadcast_translator', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-5-mini is a reasoning model with enum ["minimal","low","medium","high"]
    (gen_random_uuid(), 'context_resolver', 'openai', 'gpt-5-mini', 0.2, NULL, '{"effort":"minimal"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_classifier', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-nano is non-reasoning → effort dropped (was 'minimal')
    (gen_random_uuid(), 'memory_reference_extraction', 'openai', 'gpt-4.1-nano', 0, NULL, NULL, NOW(), NOW()),
    -- gpt-5-mini is a reasoning model → keep 'minimal'
    (gen_random_uuid(), 'memory_reference_resolution', 'openai', 'gpt-5-mini', NULL, NULL, '{"effort":"minimal"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'router', NULL, 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_pivot', NULL, 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'minimal')
    (gen_random_uuid(), 'semantic_validator', 'openai', 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'minimal')
    (gen_random_uuid(), 'query_agent', 'openai', 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'minimal')
    (gen_random_uuid(), 'query_analyzer', 'openai', 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'minimal')
    (gen_random_uuid(), 'initiative', NULL, 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'low')
    (gen_random_uuid(), 'vision_analysis', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'low')
    (gen_random_uuid(), 'voice_comment', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'low')
    (gen_random_uuid(), 'skill_description_translator', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    -- gpt-4.1-mini is non-reasoning → effort dropped (was 'low')
    (gen_random_uuid(), 'mcp_description', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),

    -- Creative / extraction entries (interest_extraction, journal_extraction,
    -- memory_extraction, hitl_plan_approval_question_generator) referenced
    -- claude-sonnet-4-6 which has been retired — rows removed entirely.
    -- Admins should re-add overrides via UI pointing at claude-sonnet-4-6.

    -- Planning (cost-effective reasoning — qwen3.5-plus)
    (gen_random_uuid(), 'planner', 'qwen', 'qwen3.5-plus', NULL, 10000, NULL, NOW(), NOW()),
    -- Qwen 'none' → toggle off
    (gen_random_uuid(), 'heartbeat_decision', 'qwen', 'qwen3.5-plus', NULL, NULL, '{"enabled":false}'::jsonb, NOW(), NOW()),

    -- Advanced (full capability — gpt-5.4 = reasoning model with enum ["none","low","medium","high","xhigh"])
    (gen_random_uuid(), 'browser_agent', 'openai', 'gpt-5.4', NULL, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_react_agent', 'openai', 'gpt-5.4', NULL, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'subagent', 'openai', 'gpt-5.4', NULL, NULL, NULL, NOW(), NOW()),

    -- Response & HITL (no provider/model bound — kept as effort hints; runtime
    -- adapter will validate against the actual model in use at call time)
    (gen_random_uuid(), 'response', NULL, NULL, 0.7, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'compaction', NULL, NULL, 0.2, NULL, '{"effort":"minimal"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_question_generator', NULL, NULL, NULL, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_message', NULL, NULL, NULL, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'interest_content', NULL, NULL, NULL, NULL, '{"effort":"low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'journal_consolidation', NULL, NULL, NULL, 10000, '{"enabled":false}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_excalidraw', NULL, NULL, 0.2, NULL, '{"effort":"medium"}'::jsonb, NOW(), NOW())

ON CONFLICT (llm_type) DO UPDATE SET
    provider = EXCLUDED.provider,
    model = EXCLUDED.model,
    temperature = EXCLUDED.temperature,
    max_tokens = EXCLUDED.max_tokens,
    reasoning_effort = EXCLUDED.reasoning_effort,
    updated_at = NOW();
