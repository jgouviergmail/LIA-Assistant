"""Startup step: freeze the heap the boot built out of the cyclic collector.

CPython's collector runs a full (generation 2) collection only once the
survivors of younger collections exceed a quarter of the long-lived objects it
already tracks. A worker holds about 1.6 million such objects after the boot —
every registry, prompt, catalogue, compiled graph and pydantic model — so a full
collection waited for some 400,000 new survivors, and what a turn left behind
in cycles (argument models, adapters, request contexts and the vectors they
held) sat in the heap meanwhile. Measured on production on 2026-10-12 (ADR-283,
amendment): a single ``gc.collect()`` in a five-hour-old worker reclaimed
123,763 objects and 120 MB.

``gc.freeze()`` moves everything alive at that point into the permanent
generation: it is neither scanned nor counted, so full collections become as
frequent as the thresholds say, and they scan only what the process allocated
since. The boot's objects are never garbage anyway — they live until the
worker exits. The one cost, accepted: a startup object REPLACED at runtime (a
configuration cache rebuilt on invalidation) keeps its frozen first version
resident — one copy, once, never one per reload. And ``gc.get_objects()`` no
longer lists the frozen heap: a census reads it through ``gc.get_freeze_count()``.
"""

import gc

import structlog

logger = structlog.get_logger(__name__)


def freeze_startup_heap() -> int:
    """Collect once, then freeze everything alive: the boot's objects leave the collector.

    Called at the END of the lifespan's startup, once every subsystem is
    resident; a second call freezes what was allocated since (idempotent in
    effect, cheap).

    Returns:
        The number of objects now in the permanent generation.
    """
    collected = gc.collect()
    gc.freeze()
    frozen = gc.get_freeze_count()
    logger.info("startup_heap_frozen", frozen_objects=frozen, collected_before=collected)
    return frozen


__all__ = ["freeze_startup_heap"]
