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
-- Two tables, both idempotent:
--   llm_models        — the capabilities catalogue (ON CONFLICT DO NOTHING:
--                       a row a migration already curated keeps its values)
--   llm_model_pricing — prices resolved by model NAME, price history kept
--                       (superseded rows ship is_active=false); the tariffs
--                       this bundle supersedes are retired, then upserted

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
    reasoning_enum_values,
    reasoning_doc_i18n_key,
    is_active
) VALUES
    ('openai', 'chatgpt-image-latest', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', NULL, NULL, false),
    ('openai', 'computer-use-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('openai', 'gpt-4.1', 1047576, 32768, true, true, true, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4.1-mini', 1047576, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4.1-nano', 1047576, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4o', 128000, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4o-2024-05-13', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4o-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', NULL, NULL, true),
    ('openai', 'gpt-4o-mini', 128000, 16384, true, true, true, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4o-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', NULL, NULL, true),
    ('openai', 'gpt-4o-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', NULL, NULL, true),
    ('openai', 'gpt-4o-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-4o-realtime-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', NULL, NULL, true),
    ('openai', 'gpt-4o-search-preview', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-5', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, 'openai_gpt5', true),
    ('openai', 'gpt-5.1', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high"]'::jsonb, 'openai_gpt5_1', true),
    ('openai', 'gpt-5.1-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-5.1-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_gpt5_1_codex', true),
    ('openai', 'gpt-5.1-codex-max', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_1_codex_max', true),
    ('openai', 'gpt-5.1-codex-mini', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_gpt5_1_codex', true),
    ('openai', 'gpt-5.2', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_2', true),
    ('openai', 'gpt-5.2-chat-latest', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', '["medium"]'::jsonb, 'openai_gpt5_2_chat_latest', true),
    ('openai', 'gpt-5.2-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_2_codex', true),
    ('openai', 'gpt-5.2-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_2_pro', true),
    ('openai', 'gpt-5.3-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-5.3-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_3_codex', true),
    ('openai', 'gpt-5.4', 1047576, 65536, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_4', true),
    ('openai', 'gpt-5.4-mini', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_4_mini', true),
    ('openai', 'gpt-5.5', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_5', true),
    ('openai', 'gpt-5.6-luna', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_6_luna', true),
    ('openai', 'gpt-5.6-sol', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_6_sol', true),
    ('openai', 'gpt-5.6-terra', 1047576, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh"]'::jsonb, 'openai_gpt5_6_terra', true),
    -- GPT-6, from developers.openai.com/api/docs/models/gpt-6-* (2026-09-23):
    -- 1 050 000-token window and 128 000 output, so 922 000 of input (the
    -- registries' convention: gpt-5 is 400K - 128K = 272K); text and image in,
    -- streaming, function calling and structured outputs. Astra reasons
    -- low..max with no off switch; Sol and Luna add `none`. They leave through
    -- the Responses API: Chat Completions takes function calling only at
    -- reasoning none.
    ('openai', 'gpt-6-astra', 922000, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh", "max"]'::jsonb, NULL, true),
    ('openai', 'gpt-6-luna', 922000, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, NULL, true),
    ('openai', 'gpt-6-sol', 922000, 128000, true, true, true, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, NULL, true),
    ('openai', 'gpt-5-chat-latest', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-5-codex', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_gpt5_codex', true),
    ('openai', 'gpt-5-mini', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, 'openai_gpt5', true),
    ('openai', 'gpt-5-nano', 1047576, 16384, true, true, true, true, true, true, false, false, false, false, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, 'openai_gpt5', true),
    ('openai', 'gpt-5-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["high"]'::jsonb, 'openai_gpt5_pro', true),
    ('openai', 'gpt-5-search-api', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('openai', 'gpt-audio', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', NULL, NULL, true),
    ('openai', 'gpt-audio-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', NULL, NULL, true),
    ('openai', 'gpt-audio-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'audio', NULL, NULL, true),
    ('openai', 'gpt-image-1', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', NULL, NULL, false),
    ('openai', 'gpt-image-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', NULL, NULL, false),
    ('openai', 'gpt-image-1-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', NULL, NULL, false),
    ('openai', 'gpt-image-2', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'image', NULL, NULL, true),
    ('openai', 'gpt-realtime', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', NULL, NULL, true),
    ('openai', 'gpt-realtime-1.5', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', NULL, NULL, true),
    ('openai', 'gpt-realtime-mini', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'realtime', NULL, NULL, true),
    ('openai', 'gpt-live-1', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('openai', 'o1', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o1-mini', 128000, 65536, true, true, true, true, true, false, false, false, false, false, 'chat', NULL, NULL, true),
    ('openai', 'o1-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o3', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o3-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', NULL, NULL, true),
    ('openai', 'o3-mini', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o3-pro', 8192, 4096, true, true, false, true, false, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o4-mini', 200000, 100000, true, true, true, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'openai_o_series', true),
    ('openai', 'o4-mini-deep-research', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'chat', NULL, NULL, true),
    ('openai', 'text-embedding-004', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('openai', 'text-embedding-3-large', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('openai', 'text-embedding-3-small', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('openai', 'text-embedding-ada-002', 8192, 0, false, false, false, false, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('openai', 'tts-1', 4096, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('openai', 'tts-1-hd', 4096, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('anthropic', 'claude-3-5-haiku-20241022', 200000, 8192, true, true, false, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('anthropic', 'claude-3-5-sonnet-20241022', 200000, 8192, true, true, false, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('anthropic', 'claude-haiku-4-5', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', NULL, 'anthropic_haiku_4_5', true),
    ('anthropic', 'claude-opus-4-5', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', NULL, 'anthropic_4_5', true),
    ('anthropic', 'claude-opus-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', '["none", "low", "medium", "high", "max"]'::jsonb, 'anthropic_4_6', true),
    ('anthropic', 'claude-sonnet-4-6', 8192, 4096, true, true, false, true, false, true, true, false, false, false, 'chat', '["none", "low", "medium", "high", "max"]'::jsonb, 'anthropic_sonnet_4_6', true),
    -- Every Claude model the Claude API serves that the catalogue lacked, read on
    -- 2026-09-23 (ADR-306): windows and effort ladders from the Models API, the
    -- rest from validation requests on the API itself. 1M in / 128K out from Opus
    -- 4.6 on; Sonnet 4.5 keeps 200K / 64K (the context-windows documentation,
    -- where the Models API reports 1M). A non-default temperature is refused
    -- from Opus 4.7 on, and top_p never reaches a Claude model (the adapter
    -- drops it).
    -- Fable 5, Fable 5.1 and Opus 5.5 cannot switch thinking off: no `none` on
    -- their ladder. The Mythos models are Project Glasswing only (absent from
    -- the Models API of an ordinary organisation), so not offered here.
    ('anthropic', 'claude-fable-5-1', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_always_on', true),
    ('anthropic', 'claude-fable-5', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_always_on', true),
    ('anthropic', 'claude-opus-5-5', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_always_on', true),
    ('anthropic', 'claude-opus-5', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_5', true),
    ('anthropic', 'claude-sonnet-5', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_5', true),
    ('anthropic', 'claude-opus-4-8', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_4_7', true),
    ('anthropic', 'claude-opus-4-7', 1000000, 128000, true, true, false, true, true, true, false, false, false, false, 'chat', '["none", "low", "medium", "high", "xhigh", "max"]'::jsonb, 'anthropic_4_7', true),
    ('anthropic', 'claude-sonnet-4-5', 200000, 64000, true, true, false, true, true, true, true, false, false, false, 'chat', NULL, 'anthropic_4_5', true),
    ('deepseek', 'deepseek-chat', 128000, 8192, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, false),
    ('deepseek', 'deepseek-reasoner', 128000, 64000, false, false, false, true, false, true, false, false, false, false, 'chat', NULL, NULL, false),
    -- deepseek-flash is the vendor's CURRENT name (DeepSeek-V4.1-Flash, vision
    -- capable); deepseek-v4-flash is the retired alias the API still accepts.
    -- The ladder is the documented low/high/max plus the off switch
    -- (api-docs.deepseek.com/guides/thinking_mode, read 2026-09-12).
    ('deepseek', 'deepseek-flash', 1000000, 384000, true, true, false, true, true, true, true, true, true, true, 'chat', '["none", "low", "high", "max"]'::jsonb, 'deepseek_v4', true),
    ('deepseek', 'deepseek-v4-flash', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', '["none", "low", "high", "max"]'::jsonb, 'deepseek_v4', true),
    ('deepseek', 'deepseek-v4-pro', 1000000, 384000, true, true, false, true, false, true, true, true, true, true, 'chat', '["none", "low", "high", "max"]'::jsonb, 'deepseek_v4', true),
    ('perplexity', 'llama-3.1-sonar-large-128k-online', 127000, 4096, false, false, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('perplexity', 'llama-3.1-sonar-small-128k-online', 127000, 4096, false, false, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('perplexity', 'sonar', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('perplexity', 'sonar-deep-research', 8192, 4096, true, true, false, true, false, true, true, true, true, true, 'chat', '["low", "medium", "high"]'::jsonb, 'perplexity_deep', true),
    ('perplexity', 'sonar-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('perplexity', 'sonar-reasoning', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('perplexity', 'sonar-reasoning-pro', 8192, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('ollama', 'llama3.1', 131072, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('ollama', 'llama3.2', 131072, 4096, true, true, false, true, true, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('ollama', 'mistral', 32768, 4096, true, true, false, true, false, false, true, true, true, true, 'chat', NULL, NULL, true),
    ('ollama', 'qwen2.5', 131072, 8192, true, true, false, true, false, false, true, true, false, true, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash', 1000000, 8192, true, true, false, true, true, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-exp', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite', 1000000, 8192, true, true, false, true, true, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-lite-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-live-001', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.0-flash-preview-image-generation', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', NULL, 'gemini_2_5', true),
    ('gemini', 'gemini-2.5-flash-image', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', NULL, NULL, false),
    ('gemini', 'gemini-2.5-flash-lite', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', NULL, 'gemini_2_5_lite', true),
    ('gemini', 'gemini-2.5-flash-lite-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    -- The live (speech-to-speech) models, ADR-300 wave 3: kind `realtime`, required
    -- by no slot, so a live model is never offered to a chat or STT slot. The
    -- native-audio name used to carry `audio`, which offered a bidi model to the
    -- voice_transcription slot. Token limits are the catalogue's defaults.
    ('gemini', 'gemini-2.5-flash-native-audio-latest', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-native-audio-preview-09-2025', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-native-audio-preview-12-2025', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true, true, false, false, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-2.5-flash-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('gemini', 'gemini-2.5-pro', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', NULL, 'gemini_2_5_pro', true),
    ('gemini', 'gemini-2.5-pro-preview-tts', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('gemini', 'gemini-3.1-flash-lite-preview', 8192, 4096, true, true, false, true, false, true, true, true, false, false, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, 'gemini_3_x_flash', true),
    ('gemini', 'gemini-3.1-flash-live-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-3.1-pro-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'gemini_3_x_pro', true),
    ('gemini', 'gemini-3.8-live', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-3.8-live-extended-thinking', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, true),
    ('gemini', 'gemini-3.5-flash', 1048576, 65536, true, true, false, true, true, true, true, true, true, true, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, NULL, true),
    ('gemini', 'gemini-3.5-flash-lite', 1000000, 65536, true, true, false, true, true, true, true, true, true, true, 'chat', NULL, NULL, true),
    ('gemini', 'gemini-3.6-flash', 1000000, 64000, true, true, false, true, true, true, true, true, true, true, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, NULL, true),
    ('gemini', 'gemini-3.7-flash', 1000000, 64000, true, true, false, true, true, true, true, true, true, true, 'chat', '["low", "medium", "high"]'::jsonb, NULL, true),
    -- gemini-3.8-flash, from ai.google.dev/gemini-api/docs/models/gemini-3.8-flash
    -- (2026-09-23): input 1 048 576 / output 65 536 tokens, text + image + video
    -- + audio + PDF in, function calling and structured outputs; thinking
    -- levels low/medium/high only — `minimal` "returns an error", so the
    -- ladder narrowing below is what keeps a slot from sending it.
    ('gemini', 'gemini-3.8-flash', 1048576, 65536, true, true, false, true, true, true, true, true, true, true, 'chat', '["low", "medium", "high"]'::jsonb, NULL, true),
    ('gemini', 'gemini-3-flash-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', '["minimal", "low", "medium", "high"]'::jsonb, 'gemini_3_x_flash', true),
    ('gemini', 'gemini-3-pro-image-preview', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'image', NULL, NULL, false),
    ('gemini', 'gemini-3-pro-preview', 1000000, 65536, true, true, false, true, true, true, true, true, false, false, 'chat', '["low", "medium", "high"]'::jsonb, 'gemini_3_x_pro', true),
    ('gemini', 'gemini-embedding-001', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'embedding', NULL, NULL, true),
    ('qwen', 'qwen3.5-flash', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_5', true),
    ('qwen', 'qwen3.5-plus', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_5', true),
    -- Four Qwen models added 2026-09-23 from their Model Studio model pages
    -- (alibabacloud.com/help/en/model-studio/qwen3-8-flash and siblings): max
    -- input 991 808, max output 131 072 (65 536 for qwen3.6-flash), thinking,
    -- function calling and structured output on all four; image and video
    -- input on the three flash models, text only on the qwen3.7-max alias
    -- (its 2026-05-20 snapshot — vision arrived with 2026-06-08).
    ('qwen', 'qwen3.6-flash', 991808, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_6', true),
    ('qwen', 'qwen3.6-plus', 1000000, 65536, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_6', true),
    ('qwen', 'qwen3.7-flash', 991808, 131072, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_7', true),
    ('qwen', 'qwen3.7-max', 991808, 131072, true, true, false, true, false, true, true, true, false, true, 'chat', NULL, 'qwen3_7', true),
    ('qwen', 'qwen3.7-plus', 991000, 128000, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_7', true),
    ('qwen', 'qwen3.8-flash', 991808, 131072, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3_8', true),
    ('qwen', 'qwen3.8-max', 1000000, 128000, true, true, false, true, true, true, true, true, false, true, 'chat', NULL, 'qwen3.8_max', true),
    ('qwen', 'qwen3-max', 262144, 65536, false, true, false, true, false, true, true, true, false, true, 'chat', NULL, 'qwen3_max', true),
    -- Qwen Image 3.0 (ADR-305), so the image slot can name them (ADR-244's
    -- referential rule). kind 'image': the window and sampling columns are the
    -- placeholders no reader consults for an image model — what the model
    -- accepts is declared in image_generation/families.py, what it costs in
    -- image_generation_pricing_seed.sql. Mirrored by migration a9d3f1c7e5b2.
    ('qwen', 'qwen-image-3.0', 8192, 4096, false, false, false, false, true, false, false, false, false, false, 'image', NULL, NULL, true),
    ('qwen', 'qwen-image-3.0-pro', 8192, 4096, false, false, false, false, true, false, false, false, false, false, 'image', NULL, NULL, true),
    ('elevenlabs', 'elevenlabs-agents', 8192, 4096, true, true, false, true, false, false, false, false, false, false, 'realtime', NULL, NULL, false),
    ('elevenlabs', 'eleven_v3_conversational', 5000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('elevenlabs', 'eleven_flash_v2_5', 40000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('elevenlabs', 'eleven_multilingual_v2', 5000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('elevenlabs', 'eleven_turbo_v2_5', 40000, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true),
    ('elevenlabs', 'scribe_v1', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', NULL, NULL, true),
    ('elevenlabs', 'scribe_v2', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', NULL, NULL, true),
    -- OpenAI transcription models (ADR-258): the meetings fallback engine when no
    -- ElevenLabs key exists. Audio-billed per minute; `-diarize` returns speakers.
    ('openai', 'gpt-4o-transcribe-diarize', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', NULL, NULL, true),
    ('openai', 'gpt-4o-mini-transcribe', 1, 1, false, false, false, false, false, false, false, false, false, false, 'audio', NULL, NULL, true),
    ('edge', 'edge-tts', 1, 1, false, false, false, true, false, false, false, false, false, false, 'tts', NULL, NULL, true)
ON CONFLICT (model_name) DO NOTHING;

-- The bundle is materialised once: the model set below is read TWICE (to retire
-- the tariffs this bundle supersedes, then to insert its own), and duplicating
-- its rows to read them twice is how the two copies drift apart.
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

-- Price audit, 2026-09-23 (migration d5f8b2a6c9e3 carries it to upgraded
-- instances; a guard test holds both equal). Every active row was read against
-- its vendor's page; the rows dated 2026-09-23 below correct eleven of them:
-- gpt-5.6-sol (it carried gpt-5.5's price), deepseek-v4-flash (a retired name
-- billed at the Flash price), gemini-3.7-flash (it carried the Batch price)
-- and gemini-3.6-flash (the 2027 price), the two Gemini speech models (text
-- in, AUDIO out), and five Qwen cache rates (on the Frankfurt Global scope an
-- implicit hit costs 20 % of the input price -- qwen3.7-plus, qwen3-max -- and
-- qwen3.5-flash, qwen3.5-plus and qwen3.6-plus have no implicit cache there,
-- only the explicit one, whose hit costs 10 %). gemini-3.6/3.7/3.8
-- Flash double on 2027-01-01 (1.50 / 0.15 / 7.50): nothing switches them, the
-- tariffs must be edited on that date. Long-context tiers are not expressed.
INSERT INTO _lia_pricing_bundle VALUES
    ('chatgpt-image-latest', 5.000000, 1.250000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('claude-haiku-4-5', 1.000000, 0.100000, 5.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-opus-4-5', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-opus-4-6', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('claude-sonnet-4-6', 3.000000, 0.300000, 15.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    -- Claude, read 2026-09-23 on platform.claude.com/docs/en/about-claude/pricing
    -- (ADR-306). `cached` is « cache hits and refreshes »: 0.1x input, except
    -- Fable 5.1 (0.025x) and Opus 5.5 (0.05x). A cache WRITE is billed 1.25x
    -- input on the 5-minute TTL (the only one LIA writes) and 2x on the 1-hour
    -- one: a multiplier of the input price for every Claude model, so it is
    -- applied by the cost computation to the written token count the API
    -- reports, never stored as a price here. Fast mode is not used.
    ('claude-fable-5-1', 10.000000, 0.250000, 50.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-fable-5', 10.000000, 1.000000, 50.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-opus-5-5', 4.000000, 0.200000, 20.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-opus-5', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-opus-4-8', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-opus-4-7', 5.000000, 0.500000, 25.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-sonnet-5', 2.000000, 0.200000, 10.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('claude-sonnet-4-5', 3.000000, 0.300000, 15.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('computer-use-preview', 3.000000, NULL, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('deepseek-chat', 0.280000, 0.028000, 0.420000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('deepseek-flash', 0.300000, 0.006000, 1.200000, 'per_1m_tokens', '2026-09-11T22:42:59.784553+00:00', true),
    ('deepseek-reasoner', 0.280000, 0.028000, 0.420000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('deepseek-v4-flash', 0.140000, 0.028000, 0.280000, 'per_1m_tokens', '2026-05-05T19:09:22.020980+00:00', false),
    ('deepseek-v4-flash', 0.440000, 0.014000, 1.320000, 'per_1m_tokens', '2026-08-14T10:02:47.659078+00:00', false),
    ('deepseek-v4-flash', 0.300000, 0.006000, 1.200000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
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
    ('gemini-2.5-flash-native-audio-latest', 0.500000, NULL, 2.000000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-2.5-flash-native-audio-preview-09-2025', 1.000000, NULL, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-flash-native-audio-preview-09-2025', 0.500000, NULL, 2.000000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-2.5-flash-native-audio-preview-12-2025', 0.500000, NULL, 2.000000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-2.5-flash-preview-09-2025', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-flash-preview-tts', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-flash-preview-tts', 0.500000, NULL, 10.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gemini-2.5-pro', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-2.5-pro-preview-tts', 1.250000, 0.125000, 10.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', false),
    ('gemini-2.5-pro-preview-tts', 1.000000, NULL, 20.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gemini-3.1-flash-lite-preview', 0.250000, 0.025000, 1.500000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3.1-flash-live-preview', 0.750000, NULL, 4.500000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-3.1-pro-preview', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-03-19T00:08:59.327299+00:00', true),
    ('gemini-3.8-live', 0.750000, NULL, 4.500000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-3.8-live-extended-thinking', 0.750000, NULL, 4.500000, 'per_1m_tokens', '2026-09-19T14:00:00+00:00', true),
    ('gemini-3.5-flash', 1.500000, 1.000000, 9.000000, 'per_1m_tokens', '2026-05-21T17:57:32.004506+00:00', false),
    ('gemini-3.5-flash', 1.500000, 0.150000, 9.000000, 'per_1m_tokens', '2026-05-21T19:34:39.408402+00:00', true),
    ('gemini-3.5-flash-lite', 0.300000, 0.030000, 2.500000, 'per_1m_tokens', '2026-08-05T19:29:06.783270+00:00', true),
    ('gemini-3.6-flash', 1.500000, 0.150000, 7.500000, 'per_1m_tokens', '2026-08-05T19:23:31.163569+00:00', false),
    ('gemini-3.6-flash', 0.750000, 0.075000, 3.750000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T09:47:36.063139+00:00', false),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T10:50:02.711915+00:00', false),
    ('gemini-3.7-flash', 0.375000, 0.037500, 1.875000, 'per_1m_tokens', '2026-08-14T10:51:38.112846+00:00', false),
    ('gemini-3.7-flash', 0.750000, 0.075000, 3.750000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    -- gemini-3.8-flash, Standard paid tier, read 2026-09-23 on
    -- ai.google.dev/gemini-api/docs/pricing: the prices valid THROUGH
    -- 2026-12-31. On 2027-01-01 they double (1.50 / 0.15 cached / 7.50) and
    -- nothing switches them: one row is active per model and a row dated in
    -- the future would retire this one at once — the tariff must be edited
    -- on that date.
    ('gemini-3.8-flash', 0.750000, 0.075000, 3.750000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
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
    ('gpt-5.6-sol', 5.000000, 0.500000, 30.000000, 'per_1m_tokens', '2026-07-28T17:05:49.595885+00:00', false),
    ('gpt-5.6-sol', 4.000000, 0.400000, 20.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gpt-5.6-terra', 2.500000, 0.250000, 15.000000, 'per_1m_tokens', '2026-07-28T17:03:53.303736+00:00', false),
    ('gpt-5.6-terra', 2.000000, 0.200000, 12.000000, 'per_1m_tokens', '2026-07-31T08:02:50.950786+00:00', true),
    -- GPT-6, Standard processing, short context, read 2026-09-23 on
    -- developers.openai.com/api/docs/pricing. Two vendor rules LIA cannot
    -- express, both making the real bill HIGHER: a prompt above 272K input
    -- tokens is billed 2x input/cache and 1.5x output for the whole request,
    -- and cache writes cost 1.25x input (counted here as plain input).
    ('gpt-6-astra', 10.000000, 1.000000, 50.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gpt-6-luna', 0.100000, 0.010000, 0.500000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gpt-6-sol', 2.000000, 0.200000, 10.000000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
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
    ('qwen3.5-flash', 0.029000, 0.020000, 0.287000, 'per_1m_tokens', '2026-04-03T19:48:04.022930+00:00', false),
    ('qwen3.5-flash', 0.029000, 0.002900, 0.287000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.5-plus', 0.115000, 0.075000, 0.688000, 'per_1m_tokens', '2026-04-03T19:49:08.410572+00:00', false),
    ('qwen3.5-plus', 0.115000, 0.011500, 0.688000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    -- Qwen, Germany (Frankfurt) region, deployment scope Global, read
    -- 2026-09-23 on alibabacloud.com/help/en/model-studio/model-pricing. A
    -- tiered model carries its FIRST tier, like its neighbours (qwen3.6-flash:
    -- up to 256K input tokens per request; qwen3.7-flash: up to 32K — beyond,
    -- the vendor bills 3x). Cached input: the implicit cache bills 20% of the
    -- input price (context-cache page), except the qwen3.8 family whose rate is
    -- published in the console only — qwen3.8-flash carries 10%, the owner's
    -- figure. qwen3.6-flash has NO implicit cache in any region (the same page's
    -- model table): its one cached rate is the explicit hit LIA marks, 10%
    -- (ADR-309).
    ('qwen3.6-flash', 0.165000, 0.016500, 0.990000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.6-plus', 0.276000, 0.180000, 1.651000, 'per_1m_tokens', '2026-04-03T20:01:03.074715+00:00', false),
    ('qwen3.6-plus', 0.276000, 0.180000, 1.651000, 'per_1m_tokens', '2026-07-03T18:10:50.321102+00:00', false),
    ('qwen3.6-plus', 0.276000, 0.027600, 1.651000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.7-flash', 0.028000, 0.005600, 0.110000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.7-max', 1.650000, 0.330000, 4.951000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:08:11.598986+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:10:18.975537+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-07-03T18:11:03.440022+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.056000, 1.101000, 'per_1m_tokens', '2026-08-03T16:36:49.954274+00:00', false),
    ('qwen3.7-plus', 0.276000, 0.055200, 1.101000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.8-flash', 0.113000, 0.011300, 0.382000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('qwen3.8-max', 1.650000, 0.206000, 4.951000, 'per_1m_tokens', '2026-08-03T16:34:15.770220+00:00', false),
    ('qwen3.8-max', 1.650000, 0.206000, 4.951000, 'per_1m_tokens', '2026-08-15T07:27:33.896260+00:00', true),
    ('qwen3-max', 0.359000, 0.240000, 1.434000, 'per_1m_tokens', '2026-04-03T20:03:46.404402+00:00', false),
    ('qwen3-max', 0.359000, 0.071800, 1.434000, 'per_1m_tokens', '2026-09-23T00:00:00+00:00', true),
    ('gpt-4o-mini-transcribe', 0.003000, NULL, 0.000000, 'per_audio_minute', '2026-09-02T12:00:00+00:00', true),
    ('gpt-4o-transcribe-diarize', 0.006000, NULL, 0.000000, 'per_audio_minute', '2026-09-02T12:00:00+00:00', true),
    ('elevenlabs-agents', 0.100000, NULL, 0.000000, 'per_audio_minute', '2026-09-19T20:00:00+00:00', false),
    ('eleven_v3_conversational', 50.000000, NULL, 0.000000, 'per_1m_tokens', '2026-09-20T12:00:00+00:00', true),
    ('gpt-live-1', 0.050000, NULL, 0.000000, 'per_audio_minute', '2026-09-19T14:00:00+00:00', true),
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
-- 06:00-10:00 UTC, all other hours at exactly 50%). Re-read 2026-09-23: the
-- peak windows apply MONDAY THROUGH FRIDAY only (« All other hours are
-- off-peak, including weekends »), so every window carries
-- "weekdays": [1, 2, 3, 4, 5] — the UTC day a window starts on, ISO numbered
-- (ADR-223 amendment). Chinese public holidays are not expressed (owner
-- decision 2026-09-23). Migration e4a7c2f9b1d6 brings upgraded instances to
-- the same windows; a guard test holds the two equal.
--
-- The demo instance's database lives in tmpfs and is rebuilt from THIS
-- bundle at every boot, so the windowed tariff must ship here — an
-- admin-UI entry would not survive a restart. Base columns become the
-- OFF-PEAK tariff (the default outside every window); the two peak windows
-- override all three prices. Idempotent by construction (absolute values).
-- ============================================================================
-- deepseek-flash (DeepSeek-V4.1-Flash): the vendor's current tariff, read on
-- 2026-09-12 from api-docs.deepseek.com/quick_start/pricing — off-peak is half
-- of peak; peak is 01:00-04:00 and 06:00-10:00 UTC on weekdays.
UPDATE llm_model_pricing p
SET input_unit_price = 0.150000,
    cached_input_unit_price = 0.003000,
    output_unit_price = 0.600000,
    time_slots = '[
      {"start_utc": "01:00", "end_utc": "04:00", "input_unit_price": 0.3, "cached_input_unit_price": 0.006, "output_unit_price": 1.2, "weekdays": [1, 2, 3, 4, 5]},
      {"start_utc": "06:00", "end_utc": "10:00", "input_unit_price": 0.3, "cached_input_unit_price": 0.006, "output_unit_price": 1.2, "weekdays": [1, 2, 3, 4, 5]}
    ]'::jsonb
FROM llm_models m
WHERE m.id = p.model_id AND m.model_name = 'deepseek-flash' AND p.is_active;

-- deepseek-v4-flash: a legacy name DeepSeek still accepts, served by
-- DeepSeek-V4.1-Flash « and billed at the Flash price » (pricing page, read
-- 2026-09-23) -- the same tariff as deepseek-flash above.
UPDATE llm_model_pricing p
SET input_unit_price = 0.150000,
    cached_input_unit_price = 0.003000,
    output_unit_price = 0.600000,
    time_slots = '[
      {"start_utc": "01:00", "end_utc": "04:00", "input_unit_price": 0.3, "cached_input_unit_price": 0.006, "output_unit_price": 1.2, "weekdays": [1, 2, 3, 4, 5]},
      {"start_utc": "06:00", "end_utc": "10:00", "input_unit_price": 0.3, "cached_input_unit_price": 0.006, "output_unit_price": 1.2, "weekdays": [1, 2, 3, 4, 5]}
    ]'::jsonb
FROM llm_models m
WHERE m.id = p.model_id AND m.model_name = 'deepseek-v4-flash' AND p.is_active;

UPDATE llm_model_pricing p
SET input_unit_price = 0.660000,
    cached_input_unit_price = 0.022000,
    output_unit_price = 1.980000,
    time_slots = '[
      {"start_utc": "01:00", "end_utc": "04:00", "input_unit_price": 1.32, "cached_input_unit_price": 0.044, "output_unit_price": 3.96, "weekdays": [1, 2, 3, 4, 5]},
      {"start_utc": "06:00", "end_utc": "10:00", "input_unit_price": 1.32, "cached_input_unit_price": 0.044, "output_unit_price": 3.96, "weekdays": [1, 2, 3, 4, 5]}
    ]'::jsonb
FROM llm_models m
WHERE m.id = p.model_id AND m.model_name = 'deepseek-v4-pro' AND p.is_active;

-- ============================================================================
-- Audio rates (ADR-300 wave 3) — a speech-to-speech model bills its audio at
-- a rate of its own, per million tokens, next to its text rate. The bundle's
-- temp table carries the three text columns only, so the audio pair is set
-- HERE, on the active row, by absolute values (idempotent). Read on
-- 2026-09-19 from ai.google.dev/gemini-api/docs/pricing: every Gemini live
-- tier bills audio at 3.00 in / 12.00 out. GPT-Live is billed by the minute
-- (per_audio_minute above) and declares no audio pair. Migration
-- f1a3c5e7b9d2 writes the same values; a guard test holds the two equal.
-- ============================================================================
UPDATE llm_model_pricing p
SET audio_input_unit_price = 3.000000,
    audio_output_unit_price = 12.000000
FROM llm_models m
WHERE m.id = p.model_id AND p.is_active AND m.model_name IN (
    'gemini-3.8-live',
    'gemini-3.8-live-extended-thinking',
    'gemini-3.1-flash-live-preview',
    'gemini-2.5-flash-native-audio-preview-09-2025',
    'gemini-2.5-flash-native-audio-preview-12-2025',
    'gemini-2.5-flash-native-audio-latest'
);

SET session_replication_role = DEFAULT;
