-- LLM Model Pricing Seed Data
-- Generated: 2026-03-12
-- Source: Production database extraction
-- Prices in USD per 1 million tokens

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Insert LLM Models catalogue (capabilities) + LLM Model Pricing (119 models)

-- ==========================================================================
-- 1) llm_models — catalogue (capabilities). One row per distinct model_name.
-- Capabilities default to a conservative profile; the admin can refine them
-- via Tarification LLM Texte (the 14-field form).
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
    is_active
) VALUES
    ('openai', 'gpt-5', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-chat-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-codex', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-nano', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5-search-api', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.1', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.1-chat-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.1-codex', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.1-codex-max', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.1-codex-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.4', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.4-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.2', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.2-chat-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.2-codex', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.2-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.3-chat-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-5.3-codex', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-2024-05-13', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-audio-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-realtime-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4o-search-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-mini-audio-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-realtime-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-mini-search-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-4.1-nano', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o1', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o1-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o1-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o3', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o3-deep-research', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o3-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o3-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o4-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'o4-mini-deep-research', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-realtime', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-realtime-1.5', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-realtime-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-audio', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-audio-1.5', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'gpt-audio-mini', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'codex-mini-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'computer-use-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'chatgpt-image-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-haiku-3', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-haiku-3-5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-haiku-3.5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-3-5-haiku-latest', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-haiku-4-5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-haiku-4.5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-3', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4-1', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4.1', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4-5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4.5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4-6', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-opus-4.6', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-3-7', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-3.7', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-4', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-4-5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-4.5', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-4-6', 8192, 4096, true, true, false, true, false, false, true),
    ('anthropic', 'claude-sonnet-4.6', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-001', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-exp', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-lite', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-lite-001', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-live-001', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.0-flash-preview-image-generation', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-image', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-image-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-lite', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-lite-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-native-audio-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-preview-09-2025', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-flash-preview-tts', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-2.5-pro-preview-tts', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-3-flash-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-3-pro-image-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-3-pro-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-3.1-flash-lite-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-3.1-pro-preview', 8192, 4096, true, true, false, true, false, false, true),
    ('deepseek', 'deepseek-chat', 8192, 4096, true, true, false, true, false, false, true),
    ('deepseek', 'deepseek-reasoner', 8192, 4096, true, true, false, true, false, false, true),
    ('perplexity', 'sonar', 8192, 4096, true, true, false, true, false, false, true),
    ('perplexity', 'sonar-deep-research', 8192, 4096, true, true, false, true, false, false, true),
    ('perplexity', 'sonar-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('perplexity', 'sonar-reasoning-pro', 8192, 4096, true, true, false, true, false, false, true),
    ('qwen', 'qwen3.6-plus', 8192, 4096, true, true, false, true, false, false, true),
    ('qwen', 'qwen3.5-plus', 8192, 4096, true, true, false, true, false, false, true),
    ('qwen', 'qwen3.5-flash', 8192, 4096, true, true, false, true, false, false, true),
    ('qwen', 'qwen3-max', 8192, 4096, true, true, false, true, false, false, true),
    ('ollama', 'llama3.2', 8192, 4096, true, true, false, true, false, false, true),
    ('ollama', 'mistral', 8192, 4096, true, true, false, true, false, false, true),
    ('qwen', 'qwen2.5', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'embedding-001', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'gemini-embedding-001', 8192, 4096, true, true, false, true, false, false, true),
    ('gemini', 'text-embedding-004', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'text-embedding-3-large', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'text-embedding-3-small', 8192, 4096, true, true, false, true, false, false, true),
    ('openai', 'text-embedding-ada-002', 8192, 4096, true, true, false, true, false, false, true)
ON CONFLICT (model_name) DO NOTHING;

-- ==========================================================================
-- 2) llm_model_pricing — pricing rows. FK to llm_models via model_id.
-- Uses INSERT ... SELECT to resolve the FK from model_name.
-- ==========================================================================
INSERT INTO llm_model_pricing (
    id,
    model_id,
    input_price_per_1m_tokens,
    cached_input_price_per_1m_tokens,
    output_price_per_1m_tokens,
    effective_from,
    is_active,
    created_at,
    updated_at
)
SELECT gen_random_uuid(), m.id, p.input, p.cached, p.output, p.effective_from::timestamptz, p.is_active, NOW(), NOW()
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
    ('gpt-4.1-mini-audio-preview', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-mini', 0.150000::numeric, 0.075000, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-mini-audio-preview', 0.150000::numeric, NULL::numeric, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-mini-realtime-preview', 0.600000::numeric, 0.300000, 2.400000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-mini-search-preview', 0.150000::numeric, NULL::numeric, 0.600000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-realtime-preview', 5.000000::numeric, 2.500000, 20.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('gpt-4.1-mini-search-preview', 2.500000::numeric, NULL::numeric, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
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
    ('codex-mini-latest', 1.500000::numeric, 0.375000, 6.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('computer-use-preview', 3.000000::numeric, NULL::numeric, 12.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('chatgpt-image-latest', 5.000000::numeric, 1.250000, 10.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-3', 0.250000::numeric, 0.030000, 1.250000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-3-5', 0.800000::numeric, 0.080000, 4.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-3.5', 0.800000::numeric, 0.080000, 4.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-3-5-haiku-latest', 0.800000::numeric, 0.080000, 4.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-4-5', 1.000000::numeric, 0.100000, 5.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-haiku-4.5', 1.000000::numeric, 0.100000, 5.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-3', 15.000000::numeric, 1.500000, 75.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4', 15.000000::numeric, 1.500000, 75.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4-1', 15.000000::numeric, 1.500000, 75.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4.1', 15.000000::numeric, 1.500000, 75.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4-5', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4.5', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4-6', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-opus-4.6', 5.000000::numeric, 0.500000, 25.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-3-7', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-3.7', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4-5', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4.5', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4-6', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
    ('claude-sonnet-4.6', 3.000000::numeric, 0.300000, 15.000000::numeric, '2026-01-01T00:00:00Z', true),
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

    IF model_count < 119 THEN
        RAISE WARNING 'Expected at least 119 models, but found %', model_count;
    END IF;
END $$;