-- LLM Configuration Seed Data
-- Generated: 2026-08-05
-- Source: Production database extraction (admin-configured settings)
--
-- Uses INSERT ... ON CONFLICT to safely merge with existing config.
-- reasoning_effort is JSONB — see docs/technical for the widget conventions.

INSERT INTO llm_config_overrides (id, llm_type, provider, model, temperature, max_tokens, reasoning_effort, created_at, updated_at)
VALUES
    (gen_random_uuid(), 'briefing', NULL, 'gpt-5.6-terra', 1.0, 5000, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'broadcast_translator', 'deepseek', 'deepseek-v4-flash', 0.5, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'browser_agent', 'deepseek', 'deepseek-v4-flash', NULL, 20000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'compaction', 'deepseek', 'deepseek-v4-flash', NULL, 50000, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'context_resolver', NULL, 'gpt-5.6-luna', NULL, 5000, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'evaluator', NULL, NULL, NULL, 500, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_decision', 'deepseek', 'deepseek-v4-flash', NULL, 10000, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_message', 'deepseek', 'deepseek-v4-flash', 0.5, 10000, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_classifier', NULL, 'gpt-5.6-luna', 0.2, 5000, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_plan_approval_question_generator', 'deepseek', 'deepseek-v4-flash', NULL, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_question_generator', 'deepseek', 'deepseek-v4-flash', NULL, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'image_generation', NULL, 'gpt-image-2', 1.0, 20000, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'initiative', 'openai', 'gpt-5.6-terra', NULL, NULL, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'interest_content', 'deepseek', 'deepseek-v4-flash', 0.5, NULL, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'interest_extraction', 'deepseek', 'deepseek-v4-flash', 0.1, 10000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'journal_consolidation', 'deepseek', 'deepseek-v4-flash', 0.2, 50000, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'journal_extraction', 'deepseek', 'deepseek-v4-flash', 0.1, 10000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_app_react_agent', NULL, NULL, NULL, 30000, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_description', 'deepseek', 'deepseek-v4-flash', 0.5, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_excalidraw', NULL, NULL, NULL, NULL, '{"effort": "low"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_react_agent', 'deepseek', 'deepseek-v4-flash', NULL, 30000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'memory_extraction', 'deepseek', 'deepseek-v4-flash', 0.1, 10000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_extraction', 'deepseek', 'deepseek-v4-flash', 0.2, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_resolution', 'deepseek', 'deepseek-v4-flash', NULL, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'open_loop_extraction', 'deepseek', 'deepseek-v4-flash', NULL, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'personality_translation', NULL, 'gpt-5.6-luna', NULL, NULL, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'planner', 'deepseek', 'deepseek-v4-flash', 0.2, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'psyche_summary', 'deepseek', 'deepseek-v4-flash', 1.0, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'query_agent', 'deepseek', 'deepseek-v4-flash', NULL, 10000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'query_analyzer', 'deepseek', 'deepseek-v4-flash', 0.2, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'react_agent', 'deepseek', 'deepseek-v4-flash', NULL, 20000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'response', 'deepseek', 'deepseek-v4-flash', 0.5, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'router', NULL, 'gpt-5.6-luna', NULL, NULL, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_pivot', NULL, 'gpt-5.6-luna', 0.2, 5000, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_validator', 'deepseek', 'deepseek-v4-flash', NULL, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'skill_description_translator', 'deepseek', 'deepseek-v4-flash', 0.5, 5000, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'subagent', 'deepseek', 'deepseek-v4-flash', NULL, NULL, '{"effort": "off"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'telephony_synthesis', 'deepseek', 'deepseek-v4-flash', 0.2, 5000, '{"effort": "high"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'vision_analysis', 'gemini', 'gemini-3.5-flash', NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'voice_comment', NULL, 'gpt-5.6-luna', NULL, 5000, '{"effort": "none"}'::jsonb, NOW(), NOW()),
    (gen_random_uuid(), 'voice_tts', 'elevenlabs', 'eleven_flash_v2_5', NULL, 10000, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'web_search_agent', NULL, NULL, 0.0, NULL, NULL, NOW(), NOW())

ON CONFLICT (llm_type) DO UPDATE SET
    provider = EXCLUDED.provider,
    model = EXCLUDED.model,
    temperature = EXCLUDED.temperature,
    max_tokens = EXCLUDED.max_tokens,
    reasoning_effort = EXCLUDED.reasoning_effort,
    updated_at = NOW();
