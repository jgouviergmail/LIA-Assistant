-- LLM Configuration Seed Data
-- Generated: 2026-11-11
-- Source: Production database extraction (admin-configured settings)
--
-- Uses INSERT ... ON CONFLICT to safely merge with existing config -- and so
-- OVERWRITES every slot it names: it is the configuration of a FRESH install,
-- never to be replayed on an instance an administrator has configured.
-- reasoning_effort is JSONB in the ADR-245 intent shape: {"level",
-- "budget_tokens", "exclude_from_output"}.
-- Full-fidelity columns: top_p, frequency_penalty, presence_penalty,
-- timeout_seconds, provider_config and context_window (ADR-278) are carried, so
-- a value an administrator sets survives the next extraction.
-- Three things are left out on purpose:
--   * a row whose slot the code no longer declares (the guard
--     test_the_configuration_seed_names_only_slots_that_exist refuses it);
--   * the voices of the speech slots: the ones production speaks with are that
--     account's choice, and a fresh install starts on the default voices the
--     code ships for the slot's provider (voice/factory.py);
--   * a slot production leaves on its code default has no row here either.
-- Every slot of a fresh install runs on a model with an active tariff
-- (test_pricing_seed_extraction_guard.py), and the providers the pipeline core
-- needs a key for are derived from these rows (llm_config/install_contract.py).

INSERT INTO llm_config_overrides (id, llm_type, provider, model, temperature, top_p, frequency_penalty, presence_penalty, max_tokens, timeout_seconds, reasoning_effort, provider_config, context_window, created_at, updated_at)
VALUES
    (gen_random_uuid(), 'briefing', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 5000, 30, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'broadcast_translator', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, NULL, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'browser_agent', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, 2, 100000, 300, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'compaction', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 300, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'diagnostician', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 300, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'discussion_context', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 900, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'discussion_decision', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'discussion_message', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'document_generation', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'email_digest', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, 30, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'emails_agent', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, NULL, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'evaluator', NULL, NULL, NULL, NULL, NULL, NULL, 500, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_decision', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 60, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'heartbeat_message', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_classifier', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_plan_approval_question_generator', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'hitl_question_generator', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'image_generation', NULL, 'gpt-image-2.6-flare', 0.5, NULL, NULL, NULL, 20000, 240, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'image_prompt_enhancement', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'initiative', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'interactive_page', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'interest_content', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'interest_extraction', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_consultation_bounded', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_consultation_path', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_email_classification', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, 5, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_event_classification', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, 5, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_hitl_exclusion', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_hitl_rejection', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_memory_reference_presence', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_observe_interests', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_observe_journal', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_observe_memory', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_observe_open_loops', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_parameter_kind', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, 5, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'jev_radio_verification', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'journal_consolidation', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 600, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'journal_extraction', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 50000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_app_react_agent', NULL, 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 30000, 300, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_description', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'mcp_react_agent', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'meeting_synthesis', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 600, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'meeting_template_selection', NULL, 'jev-1.14.0', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_extraction', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_extraction', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'memory_reference_resolution', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'open_loop_extraction', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 30, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'personality_translation', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, NULL, 30, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'planner', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, 1.6, 100000, 600, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'psyche_summary', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'query_agent', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 10000, 30, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'query_analyzer', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, 1.7, NULL, 30, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'radio_analyst', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, 120, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'radio_translator', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, 60, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'radio_verifier', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'radio_voice', 'fishaudio', 's2.1-pro-free', NULL, NULL, NULL, NULL, NULL, NULL, NULL, '{"output_format":"pcm_44100","transport":"http"}', NULL, NOW(), NOW()),
    (gen_random_uuid(), 'radio_writer', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, 60, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'react_agent', 'deepseek', 'deepseek-flash', 0.5, NULL, NULL, 1.9, 100000, 600, '{"level": "low", "budget_tokens": null, "exclude_from_output": false}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'relation_debrief', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, NULL, NULL, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'response', 'deepseek', 'deepseek-flash', NULL, NULL, NULL, NULL, 50000, NULL, NULL, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_pivot', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'semantic_validator', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'skill_description_translator', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'subagent', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 300, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'telephony_synthesis', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 100000, 120, '{"level": "medium", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'tool_assist', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, NULL, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'vision_analysis', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 10000, NULL, '{"level": "low", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'voice_comment', 'anthropic', 'claude-haiku-5-5', NULL, NULL, NULL, NULL, 5000, NULL, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW()),
    (gen_random_uuid(), 'voice_tts', 'fishaudio', 's2.1-pro-free', NULL, NULL, NULL, NULL, 10000, NULL, NULL, '{"latency":"balanced","output_format":"pcm_24000"}', NULL, NOW(), NOW()),
    (gen_random_uuid(), 'world_message_translator', 'anthropic', 'claude-sonnet-5-5', NULL, NULL, NULL, NULL, 50000, 10, '{"level": "none", "budget_tokens": null, "exclude_from_output": true}'::jsonb, NULL, NULL, NOW(), NOW())

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
    context_window = EXCLUDED.context_window,
    updated_at = NOW();
