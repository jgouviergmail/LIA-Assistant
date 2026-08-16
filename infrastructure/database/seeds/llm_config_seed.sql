-- LLM Configuration Seed Data
-- Generated: 2026-08-15
-- Source: Production database extraction (admin-configured settings)
--
-- Uses INSERT ... ON CONFLICT to safely merge with existing config.
-- reasoning_effort is JSONB — see docs/technical for the widget conventions.
-- Full-fidelity columns since 2026-08-15: top_p, frequency_penalty,
-- presence_penalty, timeout_seconds, provider_config and effort are carried
-- too (the previous generation dropped them, losing the voice-TTS tuning and
-- the per-type timeouts on fresh installs).

INSERT INTO llm_config_overrides (id, llm_type, provider, model, temperature, top_p, frequency_penalty, presence_penalty, max_tokens, timeout_seconds, reasoning_effort, provider_config, effort, created_at, updated_at)
VALUES
    (gen_random_uuid(), 'briefing', NULL, 'gpt-5.6-luna', 0.3, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'broadcast_translator', NULL, 'gpt-5.6-luna', 0.5, NULL, NULL, NULL, NULL, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'browser_agent', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, 2, 20000, 300, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'compaction', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 50000, 250, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'context_resolver', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'evaluator', NULL, NULL, NULL, NULL, NULL, NULL, 500, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_decision', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 10000, NULL, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_message', 'deepseek', 'deepseek-v4-flash', 0.3, NULL, NULL, NULL, 10000, NULL, '{"effort": "off"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_classifier', NULL, 'gpt-5.6-luna', 0.2, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_plan_approval_question_generator', 'deepseek', 'deepseek-v4-flash', 0.3, NULL, NULL, NULL, 5000, NULL, '{"effort": "off"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_question_generator', 'deepseek', 'deepseek-v4-flash', 0.3, NULL, NULL, NULL, 5000, NULL, '{"effort": "off"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'image_generation', NULL, 'gpt-image-2', 1, NULL, NULL, NULL, 20000, 240, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'initiative', 'openai', 'gpt-5.6-terra', NULL, NULL, NULL, NULL, NULL, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'interest_content', 'deepseek', 'deepseek-v4-flash', 0.3, NULL, NULL, NULL, NULL, NULL, '{"effort": "off"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'interest_extraction', NULL, 'gpt-5.6-luna', 0.1, NULL, NULL, NULL, 10000, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'journal_consolidation', 'openai', 'gpt-5.6-luna', 0.2, NULL, NULL, NULL, 50000, 500, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'journal_extraction', NULL, 'gpt-5.6-luna', 0.1, NULL, NULL, NULL, 10000, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_app_react_agent', NULL, NULL, NULL, NULL, NULL, NULL, 30000, 300, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_description', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_excalidraw', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_react_agent', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 30000, NULL, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_extraction', NULL, 'gpt-5.6-luna', 0.1, NULL, NULL, NULL, 10000, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_extraction', NULL, 'gpt-5.6-luna', 0.2, NULL, NULL, NULL, 5000, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_resolution', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 5000, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'open_loop_extraction', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'personality_translation', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, NULL, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'planner', 'openai', 'gpt-5.6-luna', 0.2, NULL, NULL, 1.6, NULL, NULL, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'psyche_summary', NULL, 'gpt-5.6-luna', 0.5, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'query_agent', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 10000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'query_analyzer', 'openai', 'gpt-5.6-luna', 0.2, 0.15, NULL, 1.7, NULL, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'react_agent', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, 1.9, 20000, NULL, '{"effort": "medium"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'response', 'deepseek', 'deepseek-v4-flash', 0.3, NULL, NULL, NULL, NULL, NULL, '{"effort": "off"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'router', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, NULL, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_pivot', NULL, 'gpt-5.6-luna', 0.2, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_validator', NULL, 'gpt-5.6-luna', NULL, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'skill_description_translator', NULL, 'gpt-5.6-luna', 0.3, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'subagent', 'openai', 'gpt-5.6-luna', NULL, NULL, NULL, NULL, NULL, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'telephony_synthesis', NULL, 'gpt-5.6-luna', 0.2, NULL, NULL, NULL, NULL, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'vision_analysis', 'gemini', 'gemini-3.7-flash', 0.5, NULL, NULL, NULL, NULL, NULL, '{"effort": "low"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'voice_comment', NULL, 'gpt-5.6-luna', 0.3, NULL, NULL, NULL, 5000, NULL, '{"effort": "none"}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'voice_tts', 'elevenlabs', 'eleven_flash_v2_5', NULL, NULL, NULL, NULL, 10000, NULL, NULL, '{"output_format":"mp3_22050_32","voice_female":"MNKK2Wl2wbbsEPQTHZGt","voice_male":"CwhRBWXzGAHq8TQ4Fs17","voice_settings":{"similarity_boost":0.5,"stability":0.5,"style":0.5,"use_speaker_boost":true}}', NULL, NOW(), NOW()),
    (gen_random_uuid(), 'web_search_agent', NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW())

ON CONFLICT (llm_type) DO UPDATE SET
    provider = EXCLUDED.provider,
    model = EXCLUDED.model,
    temperature = EXCLUDED.temperature,
    top_p = EXCLUDED.top_p,
    frequency_penalty = EXCLUDED.frequency_penalty,
    presence_penalty = EXCLUDED.presence_penalty,
    max_tokens = EXCLUDED.max_tokens,
    timeout_seconds = EXCLUDED.timeout_seconds,
    reasoning_effort = EXCLUDED.reasoning_effort,
    provider_config = EXCLUDED.provider_config,
    effort = EXCLUDED.effort,
    updated_at = NOW();
