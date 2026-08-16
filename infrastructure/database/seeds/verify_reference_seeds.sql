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
    IF c < 9 THEN
        RAISE EXCEPTION 'seed verification: google_api_pricing expected >= 9, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM image_generation_pricing;
    IF c < 27 THEN
        RAISE EXCEPTION 'seed verification: image_generation_pricing expected >= 27, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM llm_model_pricing;
    IF c < 139 THEN
        RAISE EXCEPTION 'seed verification: llm_model_pricing expected >= 139, got %', c;
    END IF;

    SELECT COUNT(*) INTO c FROM llm_config_overrides;
    IF c < 42 THEN
        RAISE EXCEPTION 'seed verification: llm_config_overrides expected >= 42, got %', c;
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
