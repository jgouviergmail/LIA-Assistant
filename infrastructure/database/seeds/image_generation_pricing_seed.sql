-- Image Generation Pricing Seed Data
-- Generated: 2026-08-05 (OpenAI rows: production database extraction)
-- Amended: 2026-09-23 (Qwen Image 3.0 rows, ADR-305)
-- Amended: 2026-09-23 (price audit, migration d5f8b2a6c9e3): gpt-image-2 carried
-- gpt-image-1's nine prices; they are now the output cost table of
-- developers.openai.com/api/docs/guides/image-generation (read 2026-09-23).
-- Prices in USD per generated image, plus, for a family that bills them per
-- image, per reference image sent to an edit (cost_per_input_image_usd).
--
-- A row is valid only when its model's family (apps/api/src/domains/
-- image_generation/families.py) accepts its quality and size, and requires or
-- refuses the reference-image price: OpenAI bills an edit's input as tokens
-- (NULL here), Qwen bills each reference image at the output's tier.
--
-- Qwen Image 3.0: Alibaba Model Studio, Germany (Frankfurt) grid, deployment
-- scope Global. The tier follows the OUTPUT area (<= 2,250,000 px is 1K); the
-- 1K sizes are OpenAI's own three, so a stored preference survives a switch.
-- Migration a9d3f1c7e5b2 carries these rows to instances that never replay
-- this bundle; a guard test holds the two equal.

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Clear existing pricing data and re-seed
DELETE FROM image_generation_pricing;

-- Insert Image Generation Pricing
INSERT INTO image_generation_pricing (
    id,
    provider,
    model,
    quality,
    size,
    cost_per_image_usd,
    cost_per_input_image_usd,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1024x1024', 0.167000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1024x1536', 0.250000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'high', '1536x1024', 0.250000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1024x1024', 0.011000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1024x1536', 0.016000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'low', '1536x1024', 0.016000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1024x1024', 0.042000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1024x1536', 0.063000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1', 'medium', '1536x1024', 0.063000, NULL, '2026-03-25T17:27:54.776359+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1024x1024', 0.133000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1024x1536', 0.200000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'high', '1536x1024', 0.200000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1024x1024', 0.009000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1024x1536', 0.013000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'low', '1536x1024', 0.013000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1024x1024', 0.034000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1024x1536', 0.050000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1.5', 'medium', '1536x1024', 0.050000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1024x1024', 0.036000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1024x1536', 0.052000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'high', '1536x1024', 0.052000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1024x1024', 0.005000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1024x1536', 0.006000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'low', '1536x1024', 0.006000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1024x1024', 0.011000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1024x1536', 0.015000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-1-mini', 'medium', '1536x1024', 0.015000, NULL, '2026-03-31T21:51:12.299426+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1024x1024', 0.211000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1024x1536', 0.165000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'high', '1536x1024', 0.165000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1024x1024', 0.006000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1024x1536', 0.005000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'low', '1536x1024', 0.005000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1024x1024', 0.053000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1024x1536', 0.041000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'openai'::llm_provider_enum, 'gpt-image-2', 'medium', '1536x1024', 0.041000, NULL, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '1024x1024', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '1536x1024', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '1024x1536', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '2048x2048', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '2448x1632', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0', 'standard', '1632x2448', 0.024754, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '1024x1024', 0.034380, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '1536x1024', 0.034380, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '1024x1536', 0.034380, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '2048x2048', 0.068761, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '2448x1632', 0.068761, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'qwen'::llm_provider_enum, 'qwen-image-3.0-pro', 'standard', '1632x2448', 0.068761, 0.002750, '2026-09-23T00:00:00+00:00', true, NOW(), NOW())
ON CONFLICT (model, quality, size, effective_from) DO NOTHING;

SET session_replication_role = DEFAULT;
