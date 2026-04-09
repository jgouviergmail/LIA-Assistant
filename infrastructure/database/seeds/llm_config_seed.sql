-- LLM Configuration Seed Data
-- Generated: 2026-04-09
-- Source: Development database (admin-configured optimal settings)
-- Contains: 45 LLM config overrides for all agent/node types
--
-- Applied on first deployment (APPLY_SEEDS=true or personalities table empty)
-- Uses INSERT ... ON CONFLICT to safely merge with existing config

-- ============================================================================
-- LLM CONFIG OVERRIDES (45 entries)
-- ============================================================================
-- Strategy:
--   - Domain agents (contacts, emails, calendar, etc.): gpt-4.1-nano (fast, cheap)
--   - Routing/analysis (router, query_analyzer, semantic): gpt-4.1-mini (balanced)
--   - Creative/extraction (journal, memory, interest): claude-sonnet-4-6 (quality)
--   - Planning (planner): qwen3.5-plus (cost-effective reasoning)
--   - Advanced (browser, subagent, mcp_react): gpt-5.4 (full capability)

INSERT INTO llm_config_overrides (id, llm_type, provider, model, temperature, max_tokens, reasoning_effort, created_at, updated_at)
VALUES
    -- Domain agents (fast, cheap — gpt-4.1-nano)
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

    -- Routing & analysis (balanced — gpt-4.1-mini)
    (gen_random_uuid(), 'broadcast_translator', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'context_resolver', 'openai', 'gpt-5-mini', 0.2, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'hitl_classifier', NULL, 'gpt-4.1-nano', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_extraction', 'openai', 'gpt-4.1-nano', 0, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_resolution', 'openai', 'gpt-5-mini', NULL, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'router', NULL, 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_pivot', NULL, 'gpt-4.1-mini', 0.2, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_validator', 'openai', 'gpt-4.1-mini', 0.2, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'query_agent', 'openai', 'gpt-4.1-mini', NULL, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'query_analyzer', 'openai', 'gpt-4.1-mini', NULL, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'initiative', NULL, 'gpt-4.1-mini', 0.2, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'vision_analysis', NULL, 'gpt-4.1-mini', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'voice_comment', NULL, 'gpt-4.1-mini', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'skill_description_translator', NULL, 'gpt-4.1-mini', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'mcp_description', NULL, 'gpt-4.1-mini', NULL, NULL, 'low', NOW(), NOW()),

    -- Creative / extraction (quality — claude-sonnet-4-6)
    (gen_random_uuid(), 'interest_extraction', 'anthropic', 'claude-sonnet-4-6', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'journal_extraction', 'anthropic', 'claude-sonnet-4-6', 0.3, 5000, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'memory_extraction', 'anthropic', 'claude-sonnet-4-6', 0.3, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'hitl_plan_approval_question_generator', 'anthropic', 'claude-sonnet-4-6', NULL, NULL, 'low', NOW(), NOW()),

    -- Planning (cost-effective reasoning — qwen3.5-plus)
    (gen_random_uuid(), 'planner', 'qwen', 'qwen3.5-plus', NULL, 10000, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_decision', 'qwen', 'qwen3.5-plus', NULL, NULL, 'none', NOW(), NOW()),

    -- Advanced (full capability — gpt-5.4)
    (gen_random_uuid(), 'browser_agent', 'openai', 'gpt-5.4', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'mcp_react_agent', 'openai', 'gpt-5.4', NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'subagent', 'openai', 'gpt-5.4', NULL, NULL, NULL, NOW(), NOW()),

    -- Response & HITL (use defaults with effort tuning)
    (gen_random_uuid(), 'response', NULL, NULL, 0.7, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'compaction', NULL, NULL, 0.2, NULL, 'minimal', NOW(), NOW()),
    (gen_random_uuid(), 'hitl_question_generator', NULL, NULL, NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_message', NULL, NULL, NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'interest_content', NULL, NULL, NULL, NULL, 'low', NOW(), NOW()),
    (gen_random_uuid(), 'journal_consolidation', NULL, NULL, NULL, 10000, 'none', NOW(), NOW()),
    (gen_random_uuid(), 'mcp_excalidraw', NULL, NULL, 0.2, NULL, 'medium', NOW(), NOW())

ON CONFLICT (llm_type) DO UPDATE SET
    provider = EXCLUDED.provider,
    model = EXCLUDED.model,
    temperature = EXCLUDED.temperature,
    max_tokens = EXCLUDED.max_tokens,
    reasoning_effort = EXCLUDED.reasoning_effort,
    updated_at = NOW();
