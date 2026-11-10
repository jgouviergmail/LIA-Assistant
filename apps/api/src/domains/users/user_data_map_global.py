"""Global (non-user) tables of the user data map: config, pricing, catalogs, admin records.

A cohesive family moved out of ``user_data_map`` when that module outgrew the
logical-SLOC cap (2026-11-08), as the ``users`` columns did before it. Every entry is
``TableDataClass.GLOBAL`` and ``ExportPolicy.EXCLUDED``: nothing here is purged with an
account or reaches its GDPR export. ``user_data_map.TABLE_RULES`` merges this table at
its end, so the guard sees one map.
"""

from src.domains.users.user_data_types import ExportPolicy, TableDataClass, TableRule

GLOBAL_TABLE_RULES: dict[str, TableRule] = {
    "admin_audit_log": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin accountability record — not user-owned data; references "
        "users but documents admin actions.",
    ),
    "admin_broadcasts": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-authored announcements, not user data.",
    ),
    "system_settings": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Instance-wide configuration.",
    ),
    "health_snapshots": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Platform self-check results (spec 2026-08-27) — no user data, "
        "pruned by the diagnostics job's own retention.",
    ),
    "incidents": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Platform incident memory (spec 2026-08-27) — alert labels and "
        "check evidence only, admin-facing, never user-owned.",
    ),
    "instance_daily_budget": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="One aggregate row per UTC day for the whole instance: no user "
        "column, no per-user attribution, nothing to purge or export.",
    ),
    **{
        table: TableRule(
            data_class=TableDataClass.GLOBAL,
            export=ExportPolicy.EXCLUDED,
            reason="JEV's instance-wide daily statistics (ADR-374): registry codes and "
            "counts per UTC day, no user column, nothing to purge or export.",
        )
        for table in (
            "jev_judgement_daily",
            "jev_outcome_daily",
            "jev_observer_agreement_daily",
        )
    },
    "personalities": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Shared personality catalog.",
    ),
    "personality_translations": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Translations of the shared personality catalog.",
    ),
    "llm_models": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="LLM catalog.",
    ),
    "llm_model_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "currency_exchange_rates": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Exchange-rate reference data.",
    ),
    "google_api_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "image_generation_pricing": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Pricing reference data.",
    ),
    "provider_api_keys": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed provider API keys (encrypted) — instance secrets.",
    ),
    "llm_config_overrides": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed LLM configuration overrides.",
    ),
    "fishaudio_pinned_voices": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Public Fish Audio voices the instance offers every voice slot (ADR-345) — "
        "admin-managed configuration; the attestation behind a pin is the audit log's record.",
    ),
    "fishaudio_catalogue_revisions": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Instance voice-library coordination: catalogue generation and pending "
        "removal tokens, independent of personal voice preferences (ADR-345).",
    ),
    "connector_global_config": TableRule(
        data_class=TableDataClass.GLOBAL,
        export=ExportPolicy.EXCLUDED,
        reason="Admin-managed connector configuration.",
    ),
}
