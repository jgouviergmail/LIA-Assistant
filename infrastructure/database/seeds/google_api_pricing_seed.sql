-- Google API Pricing Seed Data
-- Updated: 2026-08-21 (Places SKU-tier correction, lot P0)
-- Updated: 2026-09-23 (price audit, migration d5f8b2a6c9e3): Static Street View
--   is $7 per 1000, not $2; the Routes API bills three SKU tiers, and the
--   client files each call under the tier its request triggers (":pro",
--   ":enterprise" -- routes_sku_suffix). The Route Matrix is billed per
--   ELEMENT returned, so its price is per 1000 elements.
-- Source: official Google Maps Platform price list (2026-08, re-read 2026-09-23)
-- Prices in USD per 1000 requests
--
-- The Places search/details field masks request `reviews` and
-- `editorialSummary`, which bill the Enterprise + Atmosphere SKU tier
-- (NOT the Pro tier the previous seed assumed). The ":lite" endpoints are
-- the Pro-only field-mask variants tracked separately by the client.

-- Disable triggers for faster bulk insert
SET session_replication_role = replica;

-- Clear existing pricing data and re-seed
-- (no unique constraint on api_name+endpoint, so we use DELETE + INSERT)
DELETE FROM google_api_pricing;

-- Insert Google API Pricing (22 endpoints)
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
    (gen_random_uuid(), 'places', '/places/{id}', 'Place Details Enterprise + Atmosphere', 25.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchNearby', 'Nearby Search Enterprise + Atmosphere', 40.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchNearby:lite', 'Nearby Search Pro', 32.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchText', 'Text Search Enterprise + Atmosphere', 40.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'places', '/places:searchText:lite', 'Text Search Pro', 32.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/directions/v2:computeRoutes', 'Compute Routes Essentials', 5.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/directions/v2:computeRoutes:pro', 'Compute Routes Pro', 10.0000, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/directions/v2:computeRoutes:enterprise', 'Compute Routes Enterprise', 15.0000, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/distanceMatrix/v2:computeRouteMatrix', 'Compute Route Matrix Essentials', 5.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/distanceMatrix/v2:computeRouteMatrix:pro', 'Compute Route Matrix Pro', 10.0000, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'routes', '/distanceMatrix/v2:computeRouteMatrix:enterprise', 'Compute Route Matrix Enterprise', 15.0000, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'static_maps', '/staticmap', 'Static Maps', 2.0000, '2026-02-04T15:12:22.027282+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'street_view', '/streetview', 'Street View Static', 7.0000, '2026-09-23T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'street_view', '/streetview/metadata', 'Street View Metadata (free)', 0.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'weather', '/v1/currentConditions:lookup', 'Weather Current Conditions', 0.1500, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'weather', '/v1/forecast/hours:lookup', 'Weather Hourly Forecast', 0.1500, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'air_quality', '/v1/currentConditions:lookup', 'Air Quality Current Conditions', 5.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'pollen', '/v1/forecast:lookup', 'Pollen Forecast', 10.0000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW()),
    (gen_random_uuid(), 'web_risk', '/v1/uris:search', 'Web Risk Search', 0.5000, '2026-08-21T00:00:00+00:00', true, NOW(), NOW());

SET session_replication_role = DEFAULT;
