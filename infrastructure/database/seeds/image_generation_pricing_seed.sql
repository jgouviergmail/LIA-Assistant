-- Image Generation Pricing Seed Data
-- Generated: 2026-08-05
-- Source: Production database extraction
-- Prices in USD per generated image

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Clear existing pricing data and re-seed
DELETE FROM image_generation_pricing;

-- Insert Image Generation Pricing (36 rows)
INSERT INTO image_generation_pricing (
    id,
    provider,
    model,
    quality,
    size,
    cost_per_image_usd,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1024x1024', 0.167000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1024x1536', 0.250000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1536x1024', 0.250000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1024x1024', 0.011000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1024x1536', 0.016000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1536x1024', 0.016000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1024x1024', 0.042000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1024x1536', 0.063000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1536x1024', 0.063000, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1024x1024', 0.133000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1024x1536', 0.200000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1536x1024', 0.200000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1024x1024', 0.009000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1024x1536', 0.013000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1536x1024', 0.013000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1024x1024', 0.034000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1024x1536', 0.050000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1536x1024', 0.050000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1024x1024', 0.036000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1024x1536', 0.052000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1536x1024', 0.052000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1024x1024', 0.005000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1024x1536', 0.006000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1536x1024', 0.006000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1024x1024', 0.011000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1024x1536', 0.015000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1536x1024', 0.015000, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1024x1024', 0.167000, '2026-05-22T19:39:10.243168+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1024x1536', 0.250000, '2026-05-22T19:39:44.877598+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1536x1024', 0.250000, '2026-05-22T19:39:31.475096+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1024x1024', 0.011000, '2026-05-22T19:37:01.124949+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1024x1536', 0.016000, '2026-05-22T19:37:49.572851+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1536x1024', 0.016000, '2026-05-22T19:37:22.558577+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1024x1024', 0.042000, '2026-05-22T19:38:06.655116+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1024x1536', 0.063000, '2026-05-22T19:38:44.162440+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1536x1024', 0.063000, '2026-05-22T19:38:28.458306+00:00', true, NOW(), NOW())
ON CONFLICT (model, quality, size, effective_from) DO NOTHING;

SET session_replication_role = DEFAULT;
