-- LLM Model Pricing Seed Data
-- Generated: 2026-03-12
-- Updated: 2026-05-06 (reasoning_effort overhaul: 5 new columns + 25 deletions, sampling flags: 4 new columns)
-- Source: Production database extraction
-- Prices in USD per 1 million tokens

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Insert LLM Models catalogue (capabilities) + LLM Model Pricing

-- ==========================================================================
-- 1) llm_models — catalogue (capabilities). One row per distinct model_name.
-- Capabilities default to a conservative profile; the admin can refine them
-- via Tarification LLM Texte (the 14-field form).
--
-- The 5 reasoning columns (kind, reasoning_widget, reasoning_enum_values,
-- reasoning_budget_range, reasoning_doc_i18n_key) describe how the admin UI
-- should render the reasoning_effort control for each model. The 4 sampling
-- columns (supports_temperature, supports_top_p, supports_frequency_penalty,
-- supports_presence_penalty) declare which sampling parameters the model's
-- API actually accepts (philosophy A — raw truth: the UI shows only the
-- inputs that pass through to the backend).
-- ==========================================================================
INSERT INTO llm_models (
    provider,
    model_name,
    max_input_tokens,
    max_output_tokens,
    supports_tools,
    supports_structured_output,
    supports_strict_mode,
    supports_streaming,
    supports_vision,
    is_reasoning_model,
    supports_temperature,
    supports_top_p,
    supports_frequency_penalty,
    supports_presence_penalty,
    kind,
    reasoning_widget,
    reasoning_enum_values,
    reasoning_budget_range,
    reasoning_doc_i18n_key,
    is_active
) VALUES
    ('openai', 'gpt-5', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'openai_gpt5', true),
    ('openai', 'gpt-5-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-5-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_gpt5_codex', true),
    ('openai', 'gpt-5-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'openai_gpt5', true),
    ('openai', 'gpt-5-nano', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'openai_gpt5', true),
    ('openai', 'gpt-5-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["high"]'::jsonb, NULL, 'openai_gpt5_pro', true),
    ('openai', 'gpt-5-search-api', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-5.1', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["none","low","medium","high"]'::jsonb, NULL, 'openai_gpt5_1', true),
    ('openai', 'gpt-5.1-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-5.1-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_gpt5_1_codex', true),
    ('openai', 'gpt-5.1-codex-max', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_1_codex_max', true),
    ('openai', 'gpt-5.1-codex-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_gpt5_1_codex', true),
    ('openai', 'gpt-5.4', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["none","low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_4', true),
    ('openai', 'gpt-5.4-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["none","low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_4_mini', true),
    ('openai', 'gpt-5.2', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["none","low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_2', true),
    ('openai', 'gpt-5.2-chat-latest', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["medium"]'::jsonb, NULL, 'openai_gpt5_2_chat_latest', true),
    ('openai', 'gpt-5.2-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_2_codex', true),
    ('openai', 'gpt-5.2-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_2_pro', true),
    ('openai', 'gpt-5.3-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-5.3-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high","xhigh"]'::jsonb, NULL, 'openai_gpt5_3_codex', true),
    ('openai', 'gpt-4o', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-2024-05-13', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1-nano', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'o1', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o1-mini', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'o1-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o3', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o3-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'o3-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o3-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o4-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'openai_o_series', true),
    ('openai', 'o4-mini-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-realtime', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-realtime-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-realtime-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-audio', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-audio-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, true),
    ('openai', 'gpt-audio-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, true),
    ('openai', 'computer-use-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('openai', 'chatgpt-image-latest', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, true),
    ('anthropic', 'claude-haiku-4-5', 8192, 4096, true, true, false, true, false, false, true, false, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('anthropic', 'claude-opus-4-5', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'anthropic_4_5', true),
    ('anthropic', 'claude-opus-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'enum', '["low","medium","high","max"]'::jsonb, NULL, 'anthropic_4_6', true),
    ('anthropic', 'claude-sonnet-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'anthropic_sonnet_4_6', true),
    ('gemini', 'gemini-2.0-flash', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-exp', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-live-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-preview-image-generation', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"min":1,"max":24576,"off_sentinel":0,"dynamic_sentinel":-1}'::jsonb, 'gemini_2_5', true),
    ('gemini', 'gemini-2.5-flash-image', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-lite', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"min":512,"max":24576,"off_sentinel":0,"dynamic_sentinel":-1}'::jsonb, 'gemini_2_5_lite', true),
    ('gemini', 'gemini-2.5-flash-lite-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-native-audio-preview-09-2025', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-pro', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"min":128,"max":32768,"dynamic_sentinel":-1}'::jsonb, 'gemini_2_5_pro', true),
    ('gemini', 'gemini-2.5-pro-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-3-flash-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'gemini_3_x_flash', true),
    ('gemini', 'gemini-3-pro-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-3-pro-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'gemini_3_x_pro', true),
    ('gemini', 'gemini-3.1-flash-lite-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'gemini_3_x_flash', true),
    ('gemini', 'gemini-3.1-pro-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'gemini_3_x_pro', true),
    ('deepseek', 'deepseek-chat', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('deepseek', 'deepseek-reasoner', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, true),
    -- DeepSeek V4 family (v1.19.0): 1M input / 384k output, thinking-capable.
    -- See ADR-078 + LLM_PROVIDER_CONSTRAINTS.md (DeepSeek V4 section). Sampling
    -- params silently ignored when thinking is on; reasoning_effort drives
    -- extra_body.thinking.type at adapter level. is_reasoning_model=true.
    ('deepseek', 'deepseek-v4-flash', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["off","high","max"]'::jsonb, NULL, 'deepseek_v4', true),
    ('deepseek', 'deepseek-v4-pro', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["off","high","max"]'::jsonb, NULL, 'deepseek_v4', true),
    ('perplexity', 'sonar', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('perplexity', 'sonar-deep-research', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["low","medium","high"]'::jsonb, NULL, 'perplexity_deep', true),
    ('perplexity', 'sonar-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('perplexity', 'sonar-reasoning-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('qwen', 'qwen3.6-plus', 8192, 4096, true, true, false, true, false, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"min":0,"max":32768}'::jsonb, 'qwen3_5', true),
    ('qwen', 'qwen3.5-plus', 8192, 4096, true, true, false, true, false, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"min":0,"max":32768}'::jsonb, 'qwen3_5', true),
    ('qwen', 'qwen3.5-flash', 8192, 4096, true, true, false, true, false, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"min":0,"max":32768}'::jsonb, 'qwen3_5', true),
    ('qwen', 'qwen3-max', 8192, 4096, true, true, false, true, false, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"min":0,"max":32768}'::jsonb, 'qwen3_max', true),
    ('ollama', 'llama3.2', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('ollama', 'mistral', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('qwen', 'qwen2.5', 8192, 4096, true, true, false, true, false, false, true, true, false, true, 'chat', 'none', NULL, NULL, NULL, true),
    ('gemini', 'embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true),
    ('gemini', 'gemini-embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true),
    ('gemini', 'text-embedding-004', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true),
    ('openai', 'text-embedding-3-large', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true),
    ('openai', 'text-embedding-3-small', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true),
    ('openai', 'text-embedding-ada-002', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, true)
ON CONFLICT (model_name) DO NOTHING;

-- ==========================================================================
-- 2) llm_model_pricing — pricing rows. FK to llm_models via model_id.
-- Uses INSERT ... SELECT to resolve the FK from model_name.
-- Pricing rows for the 25 deleted models (gpt-4.1-mini-mini family,
-- codex-mini-latest, claude-opus-3/4/4-1/4.1/4-5/4-6, claude-sonnet-3-7/3.7/
-- 4/4-5/4.5/4-6, claude-haiku-3/3-5/3.5/3-5-latest/4-5) are also removed to
-- satisfy FK.
-- ==========================================================================
INSERT INTO llm_model_pricing (
    id,
    model_id,
    input_unit_price,
    cached_input_unit_price,
    output_unit_price,
    pricing_unit,
    effective_from,
    is_active,
    created_at,
    updated_at
)
SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output, 'per_1m_tokens'::pricing_unit_enum, p.effective_from::timestamptz, p.is_active, NOW(), NOW()
FROM (VALUES
    ('gpt-5', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-chat-latest', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-codex', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-mini', 0.250000::numeric, 0.025000, 2.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-nano', 0.050000::numeric, 0.005000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-pro', 15.000000::numeric, NULL::numeric, 120.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5-search-api', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.1', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.1-chat-latest', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.1-codex', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.1-codex-max', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.1-codex-mini', 0.250000::numeric, 0.025000, 2.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.4', 2.500000::numeric, 0.250000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.4-mini', 0.750000::numeric, 0.075000, 4.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.2', 1.750000::numeric, 0.175000, 14.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.2-chat-latest', 1.750000::numeric, 0.175000, 14.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.2-codex', 1.750000::numeric, 0.175000, 14.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.2-pro', 21.000000::numeric, NULL::numeric, 168.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.3-chat-latest', 1.750000::numeric, 0.175000, 14.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-5.3-codex', 1.750000::numeric, 0.175000, 14.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o', 2.500000::numeric, 1.250000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-2024-05-13', 5.000000::numeric, NULL::numeric, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-audio-preview', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-mini', 0.150000::numeric, 0.075000, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-mini-audio-preview', 0.150000::numeric, NULL::numeric, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-mini-realtime-preview', 0.600000::numeric, 0.300000, 2.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-mini-search-preview', 0.150000::numeric, NULL::numeric, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-realtime-preview', 5.000000::numeric, 2.500000, 20.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4o-search-preview', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1', 2.000000::numeric, 0.500000, 8.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini', 0.400000::numeric, 0.100000, 1.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-nano', 0.100000::numeric, 0.025000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('o1', 15.000000::numeric, 7.500000, 60.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('o1-mini', 1.100000::numeric, 0.550000, 4.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('o1-pro', 150.000000::numeric, NULL::numeric, 600.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('o3', 2.000000::numeric, 0.500000, 8.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('o3-deep-research', 10.000000::numeric, 2.500000, 40.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('o3-mini', 1.100000::numeric, 0.550000, 4.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('o3-pro', 20.000000::numeric, NULL::numeric, 80.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('o4-mini', 1.100000::numeric, 0.275000, 4.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('o4-mini-deep-research', 2.000000::numeric, 0.500000, 8.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-realtime', 4.000000::numeric, 0.400000, 16.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-realtime-1.5', 4.000000::numeric, 0.400000, 16.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-realtime-mini', 0.600000::numeric, 0.060000, 2.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-audio', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-audio-1.5', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-audio-mini', 0.600000::numeric, NULL::numeric, 2.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('computer-use-preview', 3.000000::numeric, NULL::numeric, 12.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('chatgpt-image-latest', 5.000000::numeric, 1.250000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-4-5', 1.000000::numeric, 0.100000, 5.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4-5', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4-6', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4-6', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash', 0.100000::numeric, 0.025000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-001', 0.100000::numeric, 0.025000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-exp', 0.100000::numeric, 0.025000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-lite', 0.075000::numeric, NULL::numeric, 0.300000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-lite-001', 0.075000::numeric, NULL::numeric, 0.300000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-live-001', 0.350000::numeric, NULL::numeric, 1.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.0-flash-preview-image-generation', 0.100000::numeric, 0.025000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash', 0.300000::numeric, 0.030000, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-image', 0.300000::numeric, 0.030000, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-image-preview', 0.300000::numeric, 0.030000, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-lite', 0.100000::numeric, 0.010000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-lite-preview-09-2025', 0.100000::numeric, 0.010000, 0.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-native-audio-preview-09-2025', 1.000000::numeric, NULL::numeric, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-preview-09-2025', 0.300000::numeric, 0.030000, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-flash-preview-tts', 0.300000::numeric, 0.030000, 2.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-pro', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-2.5-pro-preview-tts', 1.250000::numeric, 0.125000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-3-flash-preview', 0.500000::numeric, 0.050000, 3.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-3-pro-image-preview', 2.000000::numeric, 0.200000, 12.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-3-pro-preview', 2.000000::numeric, 0.200000, 12.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-3.1-flash-lite-preview', 0.250000::numeric, 0.025000, 1.500000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-3.1-pro-preview', 2.000000::numeric, 0.200000, 12.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('deepseek-chat', 0.280000::numeric, 0.028000, 0.420000::numeric, '2026-01-01T00:00:00Z', true),
    ('deepseek-reasoner', 0.280000::numeric, 0.028000, 0.420000::numeric, '2026-01-01T00:00:00Z', true),
    -- DeepSeek V4 pricing (USD per 1M tokens, official tariffs). Cache hit rate
    -- is unusually high (~50× cheaper for flash, ~120× cheaper for pro).
    ('deepseek-v4-flash', 0.140000::numeric, 0.002800, 0.280000::numeric, '2026-05-05T00:00:00Z', true),
    ('deepseek-v4-pro', 0.435000::numeric, 0.003625, 0.870000::numeric, '2026-05-05T00:00:00Z', true),
    ('sonar', 1.000000::numeric, NULL::numeric, 1.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('sonar-deep-research', 2.000000::numeric, NULL::numeric, 8.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('sonar-pro', 3.000000::numeric, NULL::numeric, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('sonar-reasoning-pro', 2.000000::numeric, NULL::numeric, 8.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('qwen3.6-plus', 0.276000::numeric, 0.180000, 1.651000::numeric, '2026-01-01T00:00:00Z', true),
    ('qwen3.5-plus', 0.115000::numeric, 0.075000, 0.688000::numeric, '2026-01-01T00:00:00Z', true),
    ('qwen3.5-flash', 0.029000::numeric, 0.020000, 0.287000::numeric, '2026-01-01T00:00:00Z', true),
    ('qwen3-max', 0.359000::numeric, 0.240000, 1.434000::numeric, '2026-01-01T00:00:00Z', true),
    ('llama3.2', 0.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('mistral', 0.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('qwen2.5', 0.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('embedding-001', 0.150000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gemini-embedding-001', 0.150000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('text-embedding-004', 0.150000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('text-embedding-3-large', 0.130000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('text-embedding-3-small', 0.020000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('text-embedding-ada-002', 0.100000::numeric, NULL::numeric, 0.000000::numeric, '2026-01-01T00:00:00Z', true)
) AS p(model_name, input, cached, output, effective_from, is_active)
JOIN llm_models m ON m.model_name = p.model_name
ON CONFLICT (model_id, effective_from) DO NOTHING;


-- ==========================================================================
-- 3) ElevenLabs Speech-to-Text models (audio-billed).
-- Scribe v2 / v1 are billed per audio hour (not tokens). The pricing_unit
-- column drives the cost computation in the runtime callbacks
-- (cf. infrastructure/cache/pricing_cache.get_cached_cost_audio_usd_eur).
-- Reference: https://elevenlabs.io/pricing/api ($0.22/hour Scribe v1/v2).
-- ==========================================================================
INSERT INTO llm_models (
    provider, model_name, max_input_tokens, max_output_tokens,
    supports_tools, supports_structured_output, supports_strict_mode,
    supports_streaming, supports_vision, is_reasoning_model,
    supports_temperature, supports_top_p, supports_frequency_penalty, supports_presence_penalty,
    kind, reasoning_widget, reasoning_enum_values, reasoning_budget_range, reasoning_doc_i18n_key,
    is_active
) VALUES
    ('elevenlabs', 'scribe_v2', 0, 0, false, false, false, false, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, true),
    ('elevenlabs', 'scribe_v1', 0, 0, false, false, false, false, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, true)
ON CONFLICT (model_name) DO NOTHING;

INSERT INTO llm_model_pricing (
    id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
    pricing_unit, effective_from, is_active, created_at, updated_at
)
SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output, 'per_audio_hour'::pricing_unit_enum,
       p.effective_from::timestamptz, p.is_active, NOW(), NOW()
FROM (VALUES
    ('scribe_v2', 0.220000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    ('scribe_v1', 0.220000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true)
) AS p(model_name, input, cached, output, effective_from, is_active)
JOIN llm_models m ON m.model_name = p.model_name
ON CONFLICT (model_id, effective_from) DO NOTHING;


-- ==========================================================================
-- 4) Text-to-Speech catalogue — Edge (free), OpenAI, ElevenLabs.
--
-- TTS is character-billed by every paid provider: characters are tracked
-- as ``prompt_tokens`` in ``token_usage_logs``, so the existing
-- per_1m_tokens accounting already produces the right cost when we set
-- ``input_unit_price`` to "USD per 1M characters".
--
-- - Edge TTS (free) gets a $0 row so it surfaces in the admin selector.
-- - OpenAI tts-1 = $15 / 1M chars, tts-1-hd = $30 / 1M chars
-- - ElevenLabs:
--     eleven_multilingual_v2 = $100 / 1M chars (HD, ~250-300ms)
--     eleven_turbo_v2_5      = $50  / 1M chars (turbo)
--     eleven_flash_v2_5      = $50  / 1M chars (~75ms ultra-low latency)
-- References:
--   https://platform.openai.com/docs/pricing
--   https://elevenlabs.io/pricing/api
-- ==========================================================================
INSERT INTO llm_models (
    provider, model_name, max_input_tokens, max_output_tokens,
    supports_tools, supports_structured_output, supports_strict_mode,
    supports_streaming, supports_vision, is_reasoning_model,
    supports_temperature, supports_top_p, supports_frequency_penalty, supports_presence_penalty,
    kind, reasoning_widget, reasoning_enum_values, reasoning_budget_range, reasoning_doc_i18n_key,
    is_active
) VALUES
    -- Edge TTS — free Microsoft Azure voice library used by the historical
    -- "standard" mode. No real model_id; the value is a placeholder so the
    -- admin can pick this provider in Configuration LLM > voice_tts.
    ('edge', 'edge-tts', 0, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    -- OpenAI TTS
    ('openai', 'tts-1', 4096, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    ('openai', 'tts-1-hd', 4096, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    -- ElevenLabs TTS
    ('elevenlabs', 'eleven_multilingual_v2', 5000, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    ('elevenlabs', 'eleven_turbo_v2_5', 40000, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true),
    ('elevenlabs', 'eleven_flash_v2_5', 40000, 0, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, true)
ON CONFLICT (model_name) DO NOTHING;

INSERT INTO llm_model_pricing (
    id, model_id, input_unit_price, cached_input_unit_price, output_unit_price,
    pricing_unit, effective_from, is_active, created_at, updated_at
)
SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output, 'per_1m_tokens'::pricing_unit_enum,
       p.effective_from::timestamptz, p.is_active, NOW(), NOW()
FROM (VALUES
    -- Edge TTS — free.
    ('edge-tts',                 0.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    -- OpenAI TTS — $/1M characters (tracked as tokens).
    ('tts-1',                   15.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    ('tts-1-hd',                30.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    -- ElevenLabs TTS — $/1M characters.
    ('eleven_multilingual_v2', 100.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    ('eleven_turbo_v2_5',       50.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true),
    ('eleven_flash_v2_5',       50.000000::numeric, NULL::numeric, 0.000000::numeric, '2026-05-07T00:00:00Z', true)
) AS p(model_name, input, cached, output, effective_from, is_active)
JOIN llm_models m ON m.model_name = p.model_name
ON CONFLICT (model_id, effective_from) DO NOTHING;


-- Insert Currency Exchange Rates
INSERT INTO currency_exchange_rates (
    id,
    from_currency,
    to_currency,
    rate,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    -- EUR to USD
    (gen_random_uuid(), 'EUR', 'USD', 1.052632, '2026-01-01T00:00:00Z', true, NOW(), NOW()),

    -- USD to EUR
    (gen_random_uuid(), 'USD', 'EUR', 0.866030, '2026-01-01T00:00:00Z', true, NOW(), NOW()),

    -- USD to USD (identity for default case)
    (gen_random_uuid(), 'USD', 'USD', 1.000000, '2026-01-01T00:00:00Z', true, NOW(), NOW())
ON CONFLICT (from_currency, to_currency, effective_from) DO NOTHING;

-- Re-enable triggers
SET session_replication_role = DEFAULT;

-- Verification queries
DO $$
DECLARE
    model_count INTEGER;
    rate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO model_count FROM llm_models WHERE is_active = true;
    SELECT COUNT(*) INTO rate_count FROM currency_exchange_rates WHERE is_active = true;

    RAISE NOTICE 'Seed completed successfully:';
    RAISE NOTICE '  - % active LLM model catalogue entries (with pricing)', model_count;
    RAISE NOTICE '  - % active currency exchange rates', rate_count;

    IF model_count < 96 THEN
        RAISE WARNING 'Expected at least 96 models, but found %', model_count;
    END IF;
END $$;