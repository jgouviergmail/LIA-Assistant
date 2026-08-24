-- Blocking reference-seed postconditions + bundle marker (ADR-215, B09).
--
-- Runs LAST inside the single seed transaction (apply_reference_seeds.sh):
-- any unmet postcondition raises, rolling back all five domains — a partial
-- seed can never commit, and a clean retry starts from the pre-seed state.
-- The marker is written in the SAME transaction so "seeded" and "verified"
-- are one atomic fact.
--
-- Counts are the audited reference-content contract (re-verified 2026-08-06):
-- exact where the content is closed (personalities), floors where the
-- catalogue can only grow (pricing/models/overrides).

DO $$
DECLARE
    c integer;
BEGIN
    SELECT COUNT(*) INTO c FROM personalities;
    IF c <> 14 THEN
        RAISE EXCEPTION 'seed verification: personalities expected 14, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM personality_translations;
    IF c <> 84 THEN
        RAISE EXCEPTION 'seed verification: personality_translations expected 84, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM google_api_pricing;
    IF c < 18 THEN
        RAISE EXCEPTION 'seed verification: google_api_pricing expected >= 18, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM image_generation_pricing;
    IF c < 27 THEN
        RAISE EXCEPTION 'seed verification: image_generation_pricing expected >= 27, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM llm_model_pricing;
    IF c < 139 THEN
        RAISE EXCEPTION 'seed verification: llm_model_pricing expected >= 139, got %', c;
    END IF;

    -- Floor lowered from 42 to 39 by ADR-244: three rows were deliberately
    -- removed, not lost -- the 'router' and 'context_resolver' slots (no
    -- get_llm() caller anywhere) and the 'mcp_excalidraw' orphan (a row for a
    -- slot that never existed in LLM_TYPES_REGISTRY).
    SELECT COUNT(*) INTO c FROM llm_config_overrides;
    IF c < 39 THEN
        RAISE EXCEPTION 'seed verification: llm_config_overrides expected >= 39, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM llm_models;
    IF c < 124 THEN
        RAISE EXCEPTION 'seed verification: llm_models expected >= 124, got %', c;
    END IF;

    -- Referential postcondition (ADR-244). Counts alone let an orphan through:
    -- llm_config_seed pinned image_generation to 'gpt-image-2' and
    -- image_generation_pricing_seed priced it, while llm_pricing_seed never
    -- created its llm_models row. ModelCapabilitiesCache then answered NULL and
    -- the runtime fell back to CONSERVATIVE_DEFAULT, silently.
    SELECT COUNT(*) INTO c
    FROM llm_config_overrides o
    WHERE o.model IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM llm_models m WHERE m.model_name = o.model);
    IF c > 0 THEN
        RAISE EXCEPTION 'seed verification: % llm_config_overrides row(s) name a model with no llm_models row', c;
    END IF;
END
$$;

-- Marker row: raw SQL writes the persisted ENUM MEMBER NAME token
-- (SQLAlchemy Enum(native_enum=False) stores member names — B09); the ORM
-- round-trip is pinned by test_reference_seed_bundle_contract.py.
-- Explicit timestamps: the mixin has no server_default.
INSERT INTO system_settings (id, key, value, change_reason, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'SELF_HOST_SEED_BUNDLE',
    :'seed_bundle_version',
    'Fresh-install reference seed bundle applied and verified (ADR-215)',
    NOW(),
    NOW()
);
