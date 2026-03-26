-- Image Generation Pricing Seed Data
-- Generated: 2026-03-25
-- Source: OpenAI pricing page
-- Prices in USD per generated image

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Clear existing pricing data and re-seed
DELETE FROM image_generation_pricing;

-- Insert Image Generation Pricing
INSERT INTO image_generation_pricing (
    id,
    model,
    quality,
    size,
    cost_per_image_usd,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    -- ========================================================================
    -- GPT-IMAGE-1 (OpenAI)
    -- ========================================================================
    (gen_random_uuid(), 'gpt-image-1', 'low', '1024x1024', 0.011000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'low', '1536x1024', 0.016000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'low', '1024x1536', 0.016000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'medium', '1024x1024', 0.042000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'medium', '1536x1024', 0.063000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'medium', '1024x1536', 0.063000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'high', '1024x1024', 0.167000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'high', '1536x1024', 0.250000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1', 'high', '1024x1536', 0.250000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- GPT-IMAGE-1.5 (OpenAI) — alias: gpt-image-latest
    -- ========================================================================
    (gen_random_uuid(), 'gpt-image-1.5', 'low', '1024x1024', 0.009000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'low', '1536x1024', 0.013000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'low', '1024x1536', 0.013000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'medium', '1024x1024', 0.034000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'medium', '1536x1024', 0.050000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'medium', '1024x1536', 0.050000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'high', '1024x1024', 0.133000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'high', '1536x1024', 0.200000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1.5', 'high', '1024x1536', 0.200000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- GPT-IMAGE-1-MINI (OpenAI)
    -- ========================================================================
    (gen_random_uuid(), 'gpt-image-1-mini', 'low', '1024x1024', 0.005000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'low', '1536x1024', 0.006000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'low', '1024x1536', 0.006000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'medium', '1024x1024', 0.011000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'medium', '1536x1024', 0.015000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'medium', '1024x1536', 0.015000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'high', '1024x1024', 0.036000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'high', '1536x1024', 0.052000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'gpt-image-1-mini', 'high', '1024x1536', 0.052000, NOW(), true, NOW(), NOW())

ON CONFLICT (model, quality, size, effective_from) DO NOTHING;

-- Re-enable triggers
SET session_replication_role = DEFAULT;

-- Verification query
DO $$
DECLARE
    pricing_count INTEGER;
    model_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO pricing_count FROM image_generation_pricing WHERE is_active = true;
    SELECT COUNT(DISTINCT model) INTO model_count FROM image_generation_pricing WHERE is_active = true;

    RAISE NOTICE 'Image Generation Pricing seed completed successfully:';
    RAISE NOTICE '  - % active pricing entries across % models', pricing_count, model_count;

    IF pricing_count < 27 THEN
        RAISE WARNING 'Expected at least 27 pricing entries, but found %', pricing_count;
    END IF;
END $$;
