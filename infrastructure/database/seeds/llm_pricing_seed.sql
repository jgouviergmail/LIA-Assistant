-- LLM Model Pricing Seed Data
-- Generated: 2026-03-12
-- Source: Production database extraction
-- Prices in USD per 1 million tokens

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Insert LLM Model Pricing (117 models)
INSERT INTO llm_model_pricing (
    id,
    model_name,
    input_price_per_1m_tokens,
    cached_input_price_per_1m_tokens,
    output_price_per_1m_tokens,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    -- ========================================================================
    -- OPENAI MODELS
    -- ========================================================================

    -- GPT-5 Series
    (gen_random_uuid(), 'gpt-5', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-chat-latest', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-codex', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-mini', 0.250000, 0.025000, 2.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-nano', 0.050000, 0.005000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-pro', 15.000000, NULL, 120.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5-search-api', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),

    -- GPT-5.1 Series
    (gen_random_uuid(), 'gpt-5.1', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.1-chat-latest', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.1-codex', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.1-codex-max', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.1-codex-mini', 0.250000, 0.025000, 2.000000, NOW(), true, NOW(), NOW()),

    -- GPT-5.4 Series
    (gen_random_uuid(), 'gpt-5.4', 2.500000, 0.250000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.4-mini', 0.750000, 0.075000, 4.500000, NOW(), true, NOW(), NOW()),

    -- GPT-5.2/5.3 Series
    (gen_random_uuid(), 'gpt-5.2', 1.750000, 0.175000, 14.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.2-chat-latest', 1.750000, 0.175000, 14.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.2-codex', 1.750000, 0.175000, 14.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.2-pro', 21.000000, NULL, 168.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.3-chat-latest', 1.750000, 0.175000, 14.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-5.3-codex', 1.750000, 0.175000, 14.000000, NOW(), true, NOW(), NOW()),

    -- GPT-4o Series
    (gen_random_uuid(), 'gpt-4o', 2.500000, 1.250000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-2024-05-13', 5.000000, NULL, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-audio-preview', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-mini', 0.150000, 0.075000, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-mini-audio-preview', 0.150000, NULL, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-mini-realtime-preview', 0.600000, 0.300000, 2.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-mini-search-preview', 0.150000, NULL, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-realtime-preview', 5.000000, 2.500000, 20.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4o-search-preview', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),

    -- GPT-4.1 Series
    (gen_random_uuid(), 'gpt-4.1', 2.000000, 0.500000, 8.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini', 0.400000, 0.100000, 1.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-audio-preview', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-mini', 0.150000, 0.075000, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-mini-audio-preview', 0.150000, NULL, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-mini-realtime-preview', 0.600000, 0.300000, 2.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-mini-search-preview', 0.150000, NULL, 0.600000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-realtime-preview', 5.000000, 2.500000, 20.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-mini-search-preview', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-4.1-nano', 0.100000, 0.025000, 0.400000, NOW(), true, NOW(), NOW()),

    -- O-Series (Reasoning Models)
    (gen_random_uuid(), 'o1', 15.000000, 7.500000, 60.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o1-mini', 1.100000, 0.550000, 4.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o1-pro', 150.000000, NULL, 600.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o3', 2.000000, 0.500000, 8.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o3-deep-research', 10.000000, 2.500000, 40.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o3-mini', 1.100000, 0.550000, 4.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o3-pro', 20.000000, NULL, 80.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o4-mini', 1.100000, 0.275000, 4.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'o4-mini-deep-research', 2.000000, 0.500000, 8.000000, NOW(), true, NOW(), NOW()),

    -- GPT Realtime/Audio/Image Series
    (gen_random_uuid(), 'gpt-realtime', 4.000000, 0.400000, 16.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-realtime-1.5', 4.000000, 0.400000, 16.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-realtime-mini', 0.600000, 0.060000, 2.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-audio', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-audio-1.5', 2.500000, NULL, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-audio-mini', 0.600000, NULL, 2.400000, NOW(), true, NOW(), NOW()),
    -- Note: gpt-image-* models are NOT text LLMs — their pricing is in
    -- image_generation_pricing table (per-image cost, not per-token).

    -- Specialized (codex, computer-use, chatgpt-image)
    (gen_random_uuid(), 'codex-mini-latest', 1.500000, 0.375000, 6.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'computer-use-preview', 3.000000, NULL, 12.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'chatgpt-image-latest', 5.000000, 1.250000, 10.000000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- ANTHROPIC CLAUDE MODELS
    -- ========================================================================

    -- Anthropic Claude Series
    (gen_random_uuid(), 'claude-haiku-3', 0.250000, 0.030000, 1.250000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-haiku-3-5', 0.800000, 0.080000, 4.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-haiku-3.5', 0.800000, 0.080000, 4.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-haiku-4-5', 1.000000, 0.100000, 5.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-haiku-4.5', 1.000000, 0.100000, 5.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-3', 15.000000, 1.500000, 75.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4', 15.000000, 1.500000, 75.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4-1', 15.000000, 1.500000, 75.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4.1', 15.000000, 1.500000, 75.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4-5', 5.000000, 0.500000, 25.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4.5', 5.000000, 0.500000, 25.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4-6', 5.000000, 0.500000, 25.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-opus-4.6', 5.000000, 0.500000, 25.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-3-7', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-3.7', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-4', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-4-5', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-4.5', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-4-6', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'claude-sonnet-4.6', 3.000000, 0.300000, 15.000000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- GOOGLE GEMINI MODELS
    -- ========================================================================

    -- Google Gemini Series
    (gen_random_uuid(), 'gemini-2.0-flash', 0.100000, 0.025000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-001', 0.100000, 0.025000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-exp', 0.100000, 0.025000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-lite', 0.075000, NULL, 0.300000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-lite-001', 0.075000, NULL, 0.300000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-live-001', 0.350000, NULL, 1.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.0-flash-preview-image-generation', 0.100000, 0.025000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash', 0.300000, 0.030000, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-image', 0.300000, 0.030000, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-image-preview', 0.300000, 0.030000, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-lite', 0.100000, 0.010000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-lite-preview-09-2025', 0.100000, 0.010000, 0.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-native-audio-preview-09-2025', 1.000000, NULL, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-preview-09-2025', 0.300000, 0.030000, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-flash-preview-tts', 0.300000, 0.030000, 2.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-pro', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-2.5-pro-preview-tts', 1.250000, 0.125000, 10.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-3-flash-preview', 0.500000, 0.050000, 3.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-3-pro-image-preview', 2.000000, 0.200000, 12.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-3-pro-preview', 2.000000, 0.200000, 12.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-3.1-flash-lite-preview', 0.250000, 0.025000, 1.500000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-3.1-pro-preview', 2.000000, 0.200000, 12.000000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- DEEPSEEK MODELS
    -- ========================================================================

    -- DeepSeek Series
    (gen_random_uuid(), 'deepseek-chat', 0.280000, 0.028000, 0.420000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'deepseek-reasoner', 0.280000, 0.028000, 0.420000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- PERPLEXITY MODELS
    -- ========================================================================

    -- Perplexity Sonar Series
    (gen_random_uuid(), 'sonar', 1.000000, NULL, 1.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'sonar-deep-research', 2.000000, NULL, 8.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'sonar-pro', 3.000000, NULL, 15.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'sonar-reasoning-pro', 2.000000, NULL, 8.000000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- QWEN MODELS (Alibaba Cloud - International pricing)
    -- ========================================================================

    -- Qwen Series (DashScope international endpoint)
    (gen_random_uuid(), 'qwen3-max', 1.200000, 0.240000, 6.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen3.5-plus', 0.400000, 0.040000, 2.400000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen3.5-flash', 0.100000, 0.010000, 0.400000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- OLLAMA LOCAL MODELS
    -- ========================================================================

    -- Ollama Local Models
    (gen_random_uuid(), 'llama3.2', 0.000000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'mistral', 0.000000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen2.5', 0.000000, NULL, 0.000000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- EMBEDDING MODELS
    -- ========================================================================

    -- Embedding Models
    (gen_random_uuid(), 'embedding-001', 0.150000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gemini-embedding-001', 0.150000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'text-embedding-004', 0.150000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'text-embedding-3-large', 0.130000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'text-embedding-3-small', 0.020000, NULL, 0.000000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'text-embedding-ada-002', 0.100000, NULL, 0.000000, NOW(), true, NOW(), NOW())

ON CONFLICT (model_name, effective_from) DO NOTHING;

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
    (gen_random_uuid(), 'EUR', 'USD', 1.052632, NOW(), true, NOW(), NOW()),

    -- USD to EUR
    (gen_random_uuid(), 'USD', 'EUR', 0.866030, NOW(), true, NOW(), NOW()),

    -- USD to USD (identity for default case)
    (gen_random_uuid(), 'USD', 'USD', 1.000000, NOW(), true, NOW(), NOW())
ON CONFLICT (from_currency, to_currency, effective_from) DO NOTHING;

-- Re-enable triggers
SET session_replication_role = DEFAULT;

-- Verification queries
DO $$
DECLARE
    model_count INTEGER;
    rate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO model_count FROM llm_model_pricing WHERE is_active = true;
    SELECT COUNT(*) INTO rate_count FROM currency_exchange_rates WHERE is_active = true;

    RAISE NOTICE 'Seed completed successfully:';
    RAISE NOTICE '  - % active LLM model pricing entries', model_count;
    RAISE NOTICE '  - % active currency exchange rates', rate_count;

    IF model_count < 117 THEN
        RAISE WARNING 'Expected at least 117 models, but found %', model_count;
    END IF;
END $$;
