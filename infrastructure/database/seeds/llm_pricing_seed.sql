-- LLM Model Pricing Seed Data
-- Generated: 2026-08-15
-- Source: Production database extraction
-- Prices in USD per the unit each row declares (per_1m_tokens for text
-- models, per_audio_hour for speech models — the unit travels with the row
-- since 2026-08-15; the previous generation hardcoded per_1m_tokens and
-- silently dropped the scribe audio-hour rows).
--
-- Since 2026-08-17 the table also carries a nullable ``time_slots`` JSONB
-- column (ADR-223, UTC windowed tariffs — DeepSeek peak/off-peak). The
-- INSERT below omits it (NULL = flat pricing, the state of the last
-- extraction); a dedicated UPDATE block at the end of this file sets the
-- official DeepSeek v4 windows — the demo database is rebuilt from this
-- bundle at every boot, so the windowed tariff must live HERE, not in an
-- admin-UI entry. The NEXT production extraction MUST include the column,
-- or every windowed tariff set through the admin UI silently reverts to
-- flat on fresh installs — the exact defect class the pricing_unit note
-- above records.
--
-- Two tables, both idempotent (ON CONFLICT DO NOTHING):
--   llm_models        — the capabilities catalogue (123 models)
--   llm_model_pricing — prices resolved by model NAME (139 rows, price
--                       history kept: superseded rows ship is_active=false)

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

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
    effort_values,
    is_active
) VALUES
    ('openai', 'chatgpt-image-latest', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('openai', 'computer-use-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1', 1047576, 32768, true, true, true, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1-mini', 1047576, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4.1-nano', 1047576, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o', 128000, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-2024-05-13', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini', 128000, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-4o-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-5', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5', NULL, true),
    ('openai', 'gpt-5.1', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5_1', NULL, true),
    ('openai', 'gpt-5.1-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-5.1-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5_1_codex', NULL, true),
    ('openai', 'gpt-5.1-codex-max', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_1_codex_max', NULL, true),
    ('openai', 'gpt-5.1-codex-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5_1_codex', NULL, true),
    ('openai', 'gpt-5.2', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_2', NULL, true),
    ('openai', 'gpt-5.2-chat-latest', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["medium"]'::jsonb, NULL, 'openai_gpt5_2_chat_latest', NULL, true),
    ('openai', 'gpt-5.2-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_2_codex', NULL, true),
    ('openai', 'gpt-5.2-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_2_pro', NULL, true),
    ('openai', 'gpt-5.3-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-5.3-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_3_codex', NULL, true),
    ('openai', 'gpt-5.4', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_4', NULL, true),
    ('openai', 'gpt-5.4-mini', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_4_mini', NULL, true),
    ('openai', 'gpt-5.5', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_5', NULL, true),
    ('openai', 'gpt-5.6-luna', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_6_luna', NULL, true),
    ('openai', 'gpt-5.6-sol', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_6_sol', NULL, true),
    ('openai', 'gpt-5.6-terra', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["none", "low", "medium", "high", "xhigh"]'::jsonb, NULL, 'openai_gpt5_6_terra', NULL, true),
    ('openai', 'gpt-5-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-5-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5_codex', NULL, true),
    ('openai', 'gpt-5-mini', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5', NULL, true),
    ('openai', 'gpt-5-nano', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, 'openai_gpt5', NULL, true),
    ('openai', 'gpt-5-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["high"]'::jsonb, NULL, 'openai_gpt5_pro', NULL, true),
    ('openai', 'gpt-5-search-api', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-audio', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-audio-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-audio-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-image-1', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('openai', 'gpt-image-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('openai', 'gpt-image-1-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('openai', 'gpt-realtime', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-realtime-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'gpt-realtime-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'o1', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o1-mini', 128000, 65536, true, true, true, true, true, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'o1-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o3', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o3-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'o3-mini', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o3-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o4-mini', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'openai_o_series', NULL, true),
    ('openai', 'o4-mini-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'text-embedding-004', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'text-embedding-3-large', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'text-embedding-3-small', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'text-embedding-ada-002', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'tts-1', 4096, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('openai', 'tts-1-hd', 4096, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('anthropic', 'claude-3-5-haiku-20241022', 200000, 8192, true, true, false, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('anthropic', 'claude-3-5-sonnet-20241022', 200000, 8192, true, true, false, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('anthropic', 'claude-haiku-4-5', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'toggle_budget', NULL, '{"max": 16384, "min": 1024}'::jsonb, 'anthropic_haiku_4_5', NULL, true),
    ('anthropic', 'claude-opus-4-5', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'toggle_budget', NULL, '{"max": 16384, "min": 1024}'::jsonb, 'anthropic_4_5', '["low", "medium", "high"]'::jsonb, true),
    ('anthropic', 'claude-opus-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'enum', '["off", "low", "medium", "high", "max"]'::jsonb, NULL, 'anthropic_4_6', NULL, true),
    ('anthropic', 'claude-sonnet-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', 'enum', '["off", "low", "medium", "high", "max"]'::jsonb, NULL, 'anthropic_sonnet_4_6', NULL, true),
    ('deepseek', 'deepseek-chat', 128000, 8192, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, false),
    ('deepseek', 'deepseek-reasoner', 128000, 64000, false, false, false, true, false, true, false, false, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, false),
    ('deepseek', 'deepseek-v4-flash', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["off", "high", "max"]'::jsonb, NULL, 'deepseek_v4', NULL, true),
    ('deepseek', 'deepseek-v4-pro', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["off", "high", "max"]'::jsonb, NULL, 'deepseek_v4', NULL, true),
    ('perplexity', 'llama-3.1-sonar-large-128k-online', 127000, 4096, false, false, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('perplexity', 'llama-3.1-sonar-small-128k-online', 127000, 4096, false, false, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('perplexity', 'sonar', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('perplexity', 'sonar-deep-research', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'perplexity_deep', NULL, true),
    ('perplexity', 'sonar-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('perplexity', 'sonar-reasoning', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('perplexity', 'sonar-reasoning-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('ollama', 'llama3.1', 131072, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('ollama', 'llama3.2', 131072, 4096, true, true, false, true, true, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('ollama', 'mistral', 32768, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('ollama', 'qwen2.5', 131072, 8192, true, true, false, true, false, false, true, true, false, true, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash', 1000000, 8192, true, true, false, true, true, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-exp', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite', 1000000, 8192, true, true, false, true, true, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-live-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-preview-image-generation', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"max": 24576, "min": 1, "off_sentinel": 0, "dynamic_sentinel": -1}'::jsonb, 'gemini_2_5', NULL, true),
    ('gemini', 'gemini-2.5-flash-image', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash-lite', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"max": 24576, "min": 512, "off_sentinel": 0, "dynamic_sentinel": -1}'::jsonb, 'gemini_2_5_lite', NULL, true),
    ('gemini', 'gemini-2.5-flash-lite-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-native-audio-preview-09-2025', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-2.5-pro', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'budget_int', NULL, '{"max": 32768, "min": 128, "dynamic_sentinel": -1}'::jsonb, 'gemini_2_5_pro', NULL, true),
    ('gemini', 'gemini-2.5-pro-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('gemini', 'gemini-3.1-flash-lite-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, 'gemini_3_x_flash', NULL, true),
    ('gemini', 'gemini-3.1-pro-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'gemini_3_x_pro', NULL, true),
    ('gemini', 'gemini-3.5-flash', 1048576, 65536, true, true, false, true, true, true, true, true, true, true, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, NULL, NULL, true),
    ('gemini', 'gemini-3.5-flash-lite', 1000000, 65536, true, true, false, true, true, true, true, true, true, true, 'chat', 'budget_int', NULL, '{"max": 24576, "min": 512, "off_sentinel": 0, "dynamic_sentinel": -1}'::jsonb, NULL, NULL, true),
    ('gemini', 'gemini-3.6-flash', 1000000, 64000, true, true, false, true, true, true, true, true, true, true, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, NULL, NULL, true),
    ('gemini', 'gemini-3.7-flash', 1000000, 64000, true, true, false, true, true, true, true, true, true, true, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, NULL, NULL, true),
    ('gemini', 'gemini-3-flash-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'enum', '["minimal", "low", "medium", "high"]'::jsonb, NULL, 'gemini_3_x_flash', NULL, true),
    ('gemini', 'gemini-3-pro-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', 'none', NULL, NULL, NULL, NULL, false),
    ('gemini', 'gemini-3-pro-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', 'enum', '["low", "medium", "high"]'::jsonb, NULL, 'gemini_3_x_pro', NULL, true),
    ('gemini', 'gemini-embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', 'none', NULL, NULL, NULL, NULL, true),
    ('qwen', 'qwen3.5-flash', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3_5', NULL, true),
    ('qwen', 'qwen3.5-plus', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3_5', NULL, true),
    ('qwen', 'qwen3.6-plus', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3_6', NULL, true),
    ('qwen', 'qwen3.7-plus', 991000, 128000, true, true, false, true, true, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3_7', NULL, true),
    ('qwen', 'qwen3.8-max', 1000000, 128000, true, true, false, true, true, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3.8_max', NULL, true),
    ('qwen', 'qwen3-max', 262144, 65536, false, true, false, true, false, true, true, true, false, true, 'chat', 'toggle_budget', NULL, '{"max": 32768, "min": 0}'::jsonb, 'qwen3_max', NULL, true),
    ('elevenlabs', 'eleven_flash_v2_5', 40000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('elevenlabs', 'eleven_multilingual_v2', 5000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('elevenlabs', 'eleven_turbo_v2_5', 40000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true),
    ('elevenlabs', 'scribe_v1', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('elevenlabs', 'scribe_v2', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', 'none', NULL, NULL, NULL, NULL, true),
    ('edge', 'edge-tts', 1, 1, false, false, false, true, false, false, false, false, false, false, 'tts', 'none', NULL, NULL, NULL, NULL, true)
ON CONFLICT (model_name) DO NOTHING;

-- The bundle is materialised once: the model set below is read TWICE (to retire
-- the tariffs this bundle supersedes, then to insert its own), and duplicating
-- 139 rows of data to read them twice is how the two copies drift apart.
DROP TABLE IF EXISTS _lia_pricing_bundle;
CREATE TEMP TABLE _lia_pricing_bundle (
    model_name      text,
    input           numeric,
    cached          numeric,
    output          numeric,
    unit            text,
    effective_from  text,
    is_active       boolean
);

INSERT INTO _lia_pricing_bundle VALUES
    ('chatgpt-image-latest', 5.000000, 1.250000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('claude-haiku-4-5', 1.000000, 0.100000, 5.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-opus-4-5', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-opus-4-6', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-sonnet-4-6', 3.000000, 0.300000, 15.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('computer-use-preview', 3.000000, NULL, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('deepseek-chat', 0.280000, 0.028000, 0.420000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('deepseek-reasoner', 0.280000, 0.028000, 0.420000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('deepseek-v4-flash', 0.140000, 0.028000, 0.280000, 'per_1m_tokens', '2026-05-05T19:09:22.020980+00:00', false),
    ('deepseek-v4-flash', 0.440000, 0.014000, 1.320000, 'per_1m_tokens', '2026-08-14T10:02:47.659078+00:00', true),
    ('deepseek-v4-pro', 0.435000, 0.003625, 0.870000, 'per_1m_tokens', '2026-05-05T19:09:58.575173+00:00', false),
    ('deepseek-v4-pro', 1.740000, 0.014500, 3.480000, 'per_1m_tokens', '2026-05-31T20:52:46.764413+00:00', false),
    ('deepseek-v4-pro', 0.435000, 0.014500, 0.870000, 'per_1m_tokens', '2026-05-31T21:13:23.740669+00:00', false),
    ('deepseek-v4-pro', 1.320000, 0.044000, 3.960000, 'per_1m_tokens', '2026-08-14T10:03:25.395615+00:00', true),
    ('edge-tts', 0.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:27:05.762899+00:00', true),
    ('eleven_flash_v2_5', 50.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:20:35.367367+00:00', false),
    ('eleven_flash_v2_5', 50.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:30:05.533720+00:00', true),
    ('eleven_multilingual_v2', 100.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:21:36.066849+00:00', true),
    ('eleven_turbo_v2_5', 50.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:22:01.375346+00:00', true),
    ('embedding-001', 0.150000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash', 0.100000, 0.025000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-001', 0.100000, 0.025000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-exp', 0.100000, 0.025000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-lite', 0.075000, NULL, 0.300000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-lite-001', 0.075000, NULL, 0.300000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-live-001', 0.350000, NULL, 1.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.0-flash-preview-image-generation', 0.100000, 0.025000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-flash', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-image', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-flash-image-preview', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-flash-lite', 0.100000, 0.010000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-lite-preview-09-2025', 0.100000, 0.010000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-native-audio-preview-09-2025', 1.000000, NULL, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-preview-09-2025', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-preview-tts', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-pro', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-pro-preview-tts', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3.1-flash-lite-preview', 0.250000, 0.025000, 1.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3.1-pro-preview', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3.5-flash', 1.500000, 1.000000, 9.000000, 'per_1m_tokens', '2026-05-21T17:57:32.004506+00:00', false),
    ('gemini-3.5-flash', 1.500000, 0.150000, 9.000000, 'per_1m_tokens', '2026-05-21T19:34:39.408402+00:00', true),
    ('gemini-3.5-flash-lite', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-08-05T19:29:06.783270+00:00', true),
    ('gemini-3.6-flash', 1.500000, 0.150000, 7.500000, 'per_1m_tokens', '2026-08-05T19:23:31.163569+00:00', true),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T09:47:36.063139+00:00', false),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T10:50:02.711915+00:00', false),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T10:51:38.112846+00:00', true),
    ('gemini-3-flash-preview', 0.500000, 0.050000, 3.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3-pro-image-preview', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-3-pro-preview', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-embedding-001', 0.150000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4.1', 2.000000, 0.500000, 8.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4.1-mini', 0.400000, 0.100000, 1.600000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4.1-nano', 0.100000, 0.025000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o', 2.500000, 1.250000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-2024-05-13', 5.000000, NULL, 15.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-audio-preview', 2.500000, NULL, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-mini', 0.150000, 0.075000, 0.600000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-mini-audio-preview', 0.150000, NULL, 0.600000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-mini-realtime-preview', 0.600000, 0.300000, 2.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-mini-search-preview', 0.150000, NULL, 0.600000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-realtime-preview', 5.000000, 2.500000, 20.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-4o-search-preview', 2.500000, NULL, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.1', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.1-chat-latest', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.1-codex', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.1-codex-max', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.1-codex-mini', 0.250000, 0.025000, 2.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.2', 1.750000, 0.175000, 14.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.2-chat-latest', 1.750000, 0.175000, 14.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.2-codex', 1.750000, 0.175000, 14.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.2-pro', 21.000000, NULL, 168.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.3-chat-latest', 1.750000, 0.175000, 14.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.3-codex', 1.750000, 0.175000, 14.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5.4', 2.500000, 0.250000, 15.000000, 'per_1m_tokens', '2026-03-23T21:49:49.339932+00:00', true),
    ('gpt-5.4-mini', 0.750000, 0.075000, 4.500000, 'per_1m_tokens', '2026-03-23T21:49:49.339932+00:00', true),
    ('gpt-5.5', 5.000000, 0.500000, 30.000000, 'per_1m_tokens', '2026-07-28T17:00:14.043038+00:00', true),
    ('gpt-5.6-luna', 1.000000, 0.100000, 6.000000, 'per_1m_tokens', '2026-07-28T17:02:17.524990+00:00', false),
    ('gpt-5.6-luna', 0.200000, 0.020000, 1.200000, 'per_1m_tokens', '2026-07-31T08:02:10.835620+00:00', true),
    ('gpt-5.6-sol', 5.000000, 0.500000, 30.000000, 'per_1m_tokens', '2026-07-28T17:05:49.595885+00:00', true),
    ('gpt-5.6-terra', 2.500000, 0.250000, 15.000000, 'per_1m_tokens', '2026-07-28T17:03:53.303736+00:00', false),
    ('gpt-5.6-terra', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-07-31T08:02:50.950786+00:00', true),
    ('gpt-5-chat-latest', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5-codex', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5-mini', 0.250000, 0.025000, 2.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5-nano', 0.050000, 0.005000, 0.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5-pro', 15.000000, NULL, 120.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-5-search-api', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-audio', 2.500000, NULL, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-audio-1.5', 2.500000, NULL, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-audio-mini', 0.600000, NULL, 2.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-image-1', 5.000000, 1.250000, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gpt-image-1', 5.000000, 1.250000, 0.000000, 'per_1m_tokens', '2026-05-07T07:43:45.511924+00:00', false),
    ('gpt-image-1.5', 5.000000, 1.250000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gpt-image-1.5', 5.000000, 1.250000, 10.000000, 'per_1m_tokens', '2026-05-07T07:43:51.764270+00:00', false),
    ('gpt-image-1-mini', 2.000000, 0.200000, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gpt-image-1-mini', 2.000000, 0.200000, 0.000000, 'per_1m_tokens', '2026-05-07T07:44:05.018511+00:00', false),
    ('gpt-realtime', 4.000000, 0.400000, 16.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-realtime-1.5', 4.000000, 0.400000, 16.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gpt-realtime-mini', 0.600000, 0.060000, 2.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('llama3.2', 0.000000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('mistral', 0.000000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('o1', 15.000000, 7.500000, 60.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o1-mini', 1.100000, 0.550000, 4.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o1-pro', 150.000000, NULL, 600.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o3', 2.000000, 0.500000, 8.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o3-deep-research', 10.000000, 2.500000, 40.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o3-mini', 1.100000, 0.550000, 4.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o3-pro', 20.000000, NULL, 80.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o4-mini', 1.100000, 0.275000, 4.400000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('o4-mini-deep-research', 2.000000, 0.500000, 8.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('qwen2.5', 0.000000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('qwen3.5-flash', 0.029000, 0.020000, 0.287000, 'per_1m_tokens', '2026-04-03T19:48:04.022930+00:00', true),
    ('qwen3.5-plus', 0.115000, 0.075000, 0.688000, 'per_1m_tokens', '2026-04-03T19:49:08.410572+00:00', true),
    ('qwen3.6-plus', 0.276000, 0.180000, 1.651000, 'per_1m_tokens', '2026-04-03T20:01:03.074715+00:00', false),
    ('qwen3.6-plus', 0.276000, 0.180000, 1.651000, 'per_1m_tokens', '2026-07-03T18:10:50.321102+00:00', true),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:08:11.598986+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:10:18.975537+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:11:03.440022+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-08-03T16:36:49.954274+00:00', true),
    ('qwen3.8-max', 1.650000, 0.206000, 4.951000, 'per_1m_tokens', '2026-08-03T16:34:15.770220+00:00', false),
    ('qwen3.8-max', 1.650000, 0.206000, 4.951000, 'per_1m_tokens', '2026-08-15T07:27:33.896260+00:00', true),
    ('qwen3-max', 0.359000, 0.240000, 1.434000, 'per_1m_tokens', '2026-04-03T20:03:46.404402+00:00', true),
    ('scribe_v1', 0.220000, NULL, 0.000000, 'per_audio_hour', '2026-05-07T23:19:14.990416+00:00', false),
    ('scribe_v1', 0.220000, NULL, 0.000000, 'per_audio_hour', '2026-05-07T23:20:54.056007+00:00', true),
    ('scribe_v2', 0.220000, NULL, 0.000000, 'per_audio_hour', '2026-05-07T23:19:49.791524+00:00', false),
    ('scribe_v2', 0.220000, NULL, 0.000000, 'per_audio_hour', '2026-05-07T23:21:01.040056+00:00', true),
    ('sonar', 1.000000, NULL, 1.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('sonar-deep-research', 2.000000, NULL, 8.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('sonar-pro', 3.000000, NULL, 15.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('sonar-reasoning', 1.000000, NULL, 5.000000, 'per_1m_tokens', '2025-12-11T00:21:29.172878+00:00', false),
    ('sonar-reasoning-pro', 2.000000, NULL, 8.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('text-embedding-004', 0.150000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('text-embedding-3-large', 0.130000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('text-embedding-3-small', 0.020000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('text-embedding-ada-002', 0.100000, NULL, 0.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('tts-1', 30.000000, NULL, 0.000001, 'per_1m_tokens', '2026-01-16T15:31:29.945630+00:00', false),
    ('tts-1', 15.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:26:05.210606+00:00', true),
    ('tts-1-hd', 30.000000, NULL, 0.000000, 'per_1m_tokens', '2026-05-07T23:26:33.641328+00:00', true)
;

-- Retire the ACTIVE tariff this bundle supersedes, BEFORE inserting its own.
-- `alembic upgrade head` runs migration `seed_openai_pricing`, which already
-- leaves one active row per model; inserting the bundle's row on top used to
-- leave BOTH active (silently, until ADR-228 added the partial unique index —
-- and that is exactly how 96 of 114 models ended up with two or three active
-- tariffs, with the read paths disagreeing on the price). Superseded rows stay
-- in the table: this retires history, it never deletes it.
UPDATE llm_model_pricing p
   SET is_active = false,
       updated_at = NOW()
  FROM llm_models m
 WHERE m.id = p.model_id
   AND p.is_active
   AND m.model_name IN (SELECT b.model_name FROM _lia_pricing_bundle b);

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
SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output,
       p.unit::pricing_unit_enum, p.effective_from::timestamptz, p.is_active, NOW(), NOW()
FROM _lia_pricing_bundle p
JOIN llm_models m ON m.model_name = p.model_name
-- DO UPDATE, never DO NOTHING: a row already standing at the SAME
-- effective_from was just deactivated above, so skipping it would leave the
-- model with NO active tariff — billed zero in silence, the defect ADR-228
-- makes the workbook state in words.
ON CONFLICT (model_id, effective_from) DO UPDATE
   SET input_unit_price        = EXCLUDED.input_unit_price,
       cached_input_unit_price = EXCLUDED.cached_input_unit_price,
       output_unit_price       = EXCLUDED.output_unit_price,
       pricing_unit            = EXCLUDED.pricing_unit,
       is_active               = EXCLUDED.is_active,
       updated_at              = NOW();

DROP TABLE _lia_pricing_bundle;

-- Enforce "exactly one active tariff per model" (partial unique index added by
-- migration 6e7f8a9b0c1d). ON CONFLICT above keys on (model_id, effective_from)
-- only, so re-running this seed against a database that already holds an
-- admin-entered row used to leave BOTH active — that is how 96 of 114 models
-- ended up with two or three active tariffs, with the read paths disagreeing on
-- the price. Retiring everything but the most recent row is safe: superseded
-- rows stay in the table as the cost history.
UPDATE llm_model_pricing p
SET is_active = false
WHERE p.is_active
  AND p.id <> (
      SELECT p2.id
      FROM llm_model_pricing p2
      WHERE p2.model_id = p.model_id AND p2.is_active
      ORDER BY p2.effective_from DESC, p2.id DESC
      LIMIT 1
  );

-- ============================================================================
-- Time-slot tariffs (ADR-223) — DeepSeek v4 official peak/off-peak windows
-- (verified 2026-08-17 on api-docs.deepseek.com: peak 01:00-04:00 and
-- 06:00-10:00 UTC, all other hours at exactly 50%).
--
-- The demo instance's database lives in tmpfs and is rebuilt from THIS
-- bundle at every boot, so the windowed tariff must ship here — an
-- admin-UI entry would not survive a restart. Base columns become the
-- OFF-PEAK tariff (the default outside every window); the two peak windows
-- override all three prices. Idempotent by construction (absolute values).
-- ============================================================================
UPDATE llm_model_pricing p
SET input_unit_price = 0.220000,
    cached_input_unit_price = 0.007000,
    output_unit_price = 0.660000,
    time_slots = '[
      {"start_utc": "01:00", "end_utc": "04:00", "input_unit_price": 0.44, "cached_input_unit_price": 0.014, "output_unit_price": 1.32},
      {"start_utc": "06:00", "end_utc": "10:00", "input_unit_price": 0.44, "cached_input_unit_price": 0.014, "output_unit_price": 1.32}
    ]'::jsonb
FROM llm_models m
WHERE m.id = p.model_id AND m.model_name = 'deepseek-v4-flash' AND p.is_active;

UPDATE llm_model_pricing p
SET input_unit_price = 0.660000,
    cached_input_unit_price = 0.022000,
    output_unit_price = 1.980000,
    time_slots = '[
      {"start_utc": "01:00", "end_utc": "04:00", "input_unit_price": 1.32, "cached_input_unit_price": 0.044, "output_unit_price": 3.96},
      {"start_utc": "06:00", "end_utc": "10:00", "input_unit_price": 1.32, "cached_input_unit_price": 0.044, "output_unit_price": 3.96}
    ]'::jsonb
FROM llm_models m
WHERE m.id = p.model_id AND m.model_name = 'deepseek-v4-pro' AND p.is_active;

SET session_replication_role = DEFAULT;
