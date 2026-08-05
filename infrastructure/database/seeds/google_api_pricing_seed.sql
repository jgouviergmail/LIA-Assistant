-- Google API Pricing Seed Data
-- Generated: 2026-08-05
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
    (gen_random_uuid(), 'geocoding', '/geocode/json', 'Geocoding', 5.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/{photo}/media', 'Place Photos', 7.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:autocomplete', 'Autocomplete', 2.8300, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places/{id}', 'Place Details Pro', 17.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchNearby', 'Nearby Search Pro', 32.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchText', 'Text Search Pro', 32.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/directions/v2:computeRoutes', 'Compute Routes', 5.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/distanceMatrix/v2:computeRouteMatrix', 'Route Matrix', 5.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'static_maps', '/staticmap', 'Static Maps', 2.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW());

SET session_replication_role = DEFAULT;
