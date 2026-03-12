-- Google API Pricing Seed Data
-- Generated: 2026-03-12
-- Source: Production database extraction
-- Prices in USD per 1000 requests

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Clear existing pricing data and re-seed
-- (no unique constraint on api_name+endpoint, so we use DELETE + INSERT)
DELETE FROM google_api_pricing;

-- Insert Google API Pricing (9 endpoints)
INSERT INTO google_api_pricing (
    id,
    api_name,
    endpoint,
    sku_name,
    cost_per_1000_usd,
    effective_from,
    is_active,
    created_at,
    updated_at
) VALUES
    -- ========================================================================
    -- GEOCODING API
    -- ========================================================================
    (gen_random_uuid(), 'geocoding', '/geocode/json', 'Geocoding', 5.0000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- PLACES API (New)
    -- ========================================================================
    (gen_random_uuid(), 'places', '/{photo}/media', 'Place Photos', 7.0000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:autocomplete', 'Autocomplete', 2.8300, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places/{id}', 'Place Details Pro', 17.0000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchNearby', 'Nearby Search Pro', 32.0000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchText', 'Text Search Pro', 32.0000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- ROUTES API
    -- ========================================================================
    (gen_random_uuid(), 'routes', '/directions/v2:computeRoutes', 'Compute Routes', 5.0000, NOW(), true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/distanceMatrix/v2:computeRouteMatrix', 'Route Matrix', 5.0000, NOW(), true, NOW(), NOW()),

    -- ========================================================================
    -- STATIC MAPS API
    -- ========================================================================
    (gen_random_uuid(), 'static_maps', '/staticmap', 'Static Maps', 2.0000, NOW(), true, NOW(), NOW());

-- Re-enable triggers
SET session_replication_role = DEFAULT;

-- Verification query
DO $$
DECLARE
    pricing_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO pricing_count FROM google_api_pricing WHERE is_active = true;

    RAISE NOTICE 'Google API Pricing seed completed successfully:';
    RAISE NOTICE '  - % active pricing entries', pricing_count;

    IF pricing_count < 9 THEN
        RAISE WARNING 'Expected at least 9 pricing entries, but found %', pricing_count;
    END IF;
END $$;
