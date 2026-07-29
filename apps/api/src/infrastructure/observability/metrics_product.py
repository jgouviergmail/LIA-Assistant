"""Prometheus transport for product analytics (ADR-178, dashboard 26).

Bounded by construction: every label value comes from the vocabularies in
``domains/product/constants.py``. Cardinality contract (program spec,
correction #8): counters carry at most 3 bounded labels, gauges carry tiny
enumerations, histograms would carry <= 2 labels (none in v1), and the
forbidden label names (``job``, ``user_id``, ``run_id``, ``result_id``)
never appear — ``job`` is reserved by the Prometheus scrape and would be
mangled to ``exported_job``.

The gauges are DB-backed (pattern ``lifetime_metrics.py``): the exact,
deduplicated SQL truth is computed by ``ProductRepository`` and merely
transported here. The North Star is NEVER derived from the counter.
"""

import time

import structlog
from prometheus_client import Counter, Gauge, Histogram

from src.domains.product.constants import (
    DATA_QUALITY_CHECKS,
    FUNNEL_STAGES,
    GAUGE_WINDOWS,
    PRODUCT_REFRESH_JOB,
    RETENTION_PERIODS,
    USEFUL_EVIDENCE_SELECTORS,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Counter — outcome lifecycle events (E3 at production, E1/E2 at validation;
# a given outcome is validated at most once, so E1|E2 increases over a window
# equal the unique validated outcomes of that window)
# ---------------------------------------------------------------------------

product_outcomes_total = Counter(
    "product_outcomes_total",
    "Product outcome events by result type, domain and evidence level "
    "(E3 incremented at production, E1/E2 at validation — validation happens "
    "at most once per outcome)",
    ["result_type", "domain", "evidence"],
)

# ---------------------------------------------------------------------------
# DB-backed gauges (restart-safe, multiprocess mostrecent)
# ---------------------------------------------------------------------------

product_users_with_useful_outcome = Gauge(
    "product_users_with_useful_outcome",
    "Distinct users with >=1 validated E1/E2 outcome in the rolling window "
    "(North Star transport — exact dedup computed in PostgreSQL)",
    ["window", "evidence"],
    multiprocess_mode="mostrecent",
)

product_value_penetration_ratio = Gauge(
    "product_value_penetration_ratio",
    "Useful users / engaged users in the rolling window (0-1), overall and "
    "per device class (v1 engaged = users with >=1 produced outcome)",
    ["window", "device_class"],
    multiprocess_mode="mostrecent",
)

product_activation_rate = Gauge(
    "product_activation_rate",
    "Signup-cohort users reaching a first validated outcome within 7 days " "of signup (0-1)",
    ["window", "path", "device_class"],
    multiprocess_mode="mostrecent",
)

product_retention_rate = Gauge(
    "product_retention_rate",
    "Rolling useful-retention: previous-period validated users validating "
    "again in the current period (0-1)",
    ["period", "segment"],
    multiprocess_mode="mostrecent",
)

product_funnel_users = Gauge(
    "product_funnel_users",
    "Distinct users at each v1 funnel stage over the rolling window "
    "(registered / technical_result / useful_result)",
    ["stage", "window", "device_class"],
    multiprocess_mode="mostrecent",
)

product_data_quality_ratio = Gauge(
    "product_data_quality_ratio",
    "Bounded product data-quality checks (0-1): domain coverage, cost "
    "backfill coverage, event-run linkage",
    ["check"],
    multiprocess_mode="mostrecent",
)

# ---------------------------------------------------------------------------
# Client telemetry (Phase 4) — bounded vocabularies, <= 2 labels on histograms
# ---------------------------------------------------------------------------

product_client_events_total = Counter(
    "product_client_events_total",
    "Accepted client telemetry events by bounded type and channel "
    "(funnel + PWA; anonymous pre-signup events allowed by arbitration a)",
    ["event_type", "channel"],
)

product_search_total = Counter(
    "product_search_total",
    "In-app search telemetry by surface and outcome "
    "(results / zero_results / result_used — SEA family)",
    ["surface", "outcome", "device_class"],
)

product_web_vital_seconds = Histogram(
    "product_web_vital_seconds",
    "Seconds-valued Web Vitals (LCP; INP deferred) by device class — "
    "sampled client-side (NEXT_PUBLIC_WEB_VITALS_SAMPLE_RATE)",
    ["metric", "device_class"],
    buckets=[0.25, 0.5, 1.0, 1.5, 2.5, 4.0, 6.0, 10.0, 20.0],
)

product_web_vital_ratio = Histogram(
    "product_web_vital_ratio",
    "Unitless Web Vitals (CLS) by device class",
    ["metric", "device_class"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0],
)

product_metrics_last_refresh_timestamp_seconds = Gauge(
    "product_metrics_last_refresh_timestamp_seconds",
    "Unix timestamp of the last successful product aggregate refresh "
    "(freshness SLA 2h — label refresh_job, NEVER 'job' which is reserved "
    "by the Prometheus scrape)",
    ["refresh_job"],
    multiprocess_mode="mostrecent",
)


def track_outcome_event(result_type: str, domain: str, evidence: str) -> None:
    """Increment the outcome counter with bounded labels.

    Args:
        result_type: Bounded ``RESULT_TYPES`` value.
        domain: Bounded domain or ``unknown``.
        evidence: ``E1`` | ``E2`` | ``E3``.
    """
    product_outcomes_total.labels(result_type=result_type, domain=domain, evidence=evidence).inc()


async def refresh_product_gauges() -> None:
    """Recompute every DB-backed product gauge from PostgreSQL.

    Called by the hourly rollup job (leader-elected). Opens its own session
    (never shared across tasks) and stamps the freshness gauge only on full
    success — a partial refresh must trip the freshness SLA, not hide it.
    """
    from src.domains.product.repository import ProductRepository
    from src.infrastructure.database import get_db_context

    # Snapshot semantics: these families are fully recomputed each refresh;
    # clearing first prevents a vanished label combination (a device class or
    # quality check with no data this window) from lingering at a stale value.
    for family in (
        product_users_with_useful_outcome,
        product_value_penetration_ratio,
        product_activation_rate,
        product_retention_rate,
        product_funnel_users,
        product_data_quality_ratio,
    ):
        family.clear()

    async with get_db_context() as db:
        repo = ProductRepository(db)

        for window_label, days in zip(GAUGE_WINDOWS, (7, 30), strict=True):
            for evidence in USEFUL_EVIDENCE_SELECTORS:
                count = await repo.count_useful_users(days, evidence)
                product_users_with_useful_outcome.labels(
                    window=window_label, evidence=evidence
                ).set(count)

            for device, ratio in (await repo.penetration_by_device(days)).items():
                product_value_penetration_ratio.labels(
                    window=window_label, device_class=device
                ).set(ratio)

            activation = await repo.activation_rate(days)
            if activation is not None:
                product_activation_rate.labels(
                    window=window_label, path="all", device_class="all"
                ).set(activation)

            for stage, count in (await repo.funnel_counts(days)).items():
                if stage not in FUNNEL_STAGES:  # defensive vocabulary guard
                    logger.warning("product_funnel_unknown_stage", stage=stage)
                    continue
                product_funnel_users.labels(
                    stage=stage, window=window_label, device_class="all"
                ).set(count)

        for period_label, days in zip(RETENTION_PERIODS, (1, 7, 30), strict=True):
            retention = await repo.retention_rate(days)
            if retention is not None:
                product_retention_rate.labels(period=period_label, segment="all").set(retention)

        for check, ratio in (await repo.data_quality_ratios()).items():
            if check not in DATA_QUALITY_CHECKS:  # defensive vocabulary guard
                logger.warning("product_quality_unknown_check", check=check)
                continue
            product_data_quality_ratio.labels(check=check).set(ratio)

    product_metrics_last_refresh_timestamp_seconds.labels(refresh_job=PRODUCT_REFRESH_JOB).set(
        time.time()
    )
