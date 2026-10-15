"""The entry a FOR_EACH writes under its own step id once its items have run.

After expansion, ``step_2`` runs as ``step_2_item_0``, ``step_2_item_1``…, yet
later steps still reference ``$steps.step_2.places`` and the plan's mapper only
reads the plan's own steps. The aggregate written under ``step_2`` serves both.

It is built from the items that SUCCEEDED (ADR-347). It used to merge every
item, so the only ``success`` value it met was a failed item's ``False``: one
failure out of three made the whole aggregate a failure, the mapper dropped it,
and the response lost every confirmation and every result of the loop. A
partial failure is now a success carrying its failed items
(``FIELD_FOR_EACH_FAILED_ITEMS``) — the field states the partial, never the
status (ADR-303) — and only a loop whose every item failed is a failure.
"""

from __future__ import annotations

import structlog

from src.core.field_names import (
    FIELD_ERROR,
    FIELD_ERROR_CODE,
    FIELD_FOR_EACH_AGGREGATE,
    FIELD_FOR_EACH_FAILED_ITEMS,
    FIELD_RESULT,
    FIELD_STEP_ID,
    FIELD_SUCCESS,
)

logger = structlog.get_logger(__name__)


def aggregate_for_each_results(
    completed_steps: dict[str, dict[str, object]],
    original_step_id: str,
    expanded_step_ids: list[str],
) -> None:
    """Write the aggregate of a FOR_EACH's items under its original step id.

    Example::

        completed_steps["step_2_item_0"] = {"places": [a, b]}
        completed_steps["step_2_item_1"] = {"success": False, "error": "…"}
        completed_steps["step_2_item_2"] = {"places": [c]}
        # becomes, under "step_2":
        {"places": [a, b, c], FIELD_FOR_EACH_FAILED_ITEMS: [{"step_id":
         "step_2_item_1", "error": "…", "error_code": None}],
         FIELD_FOR_EACH_AGGREGATE: True}

    Args:
        completed_steps: Results of the completed steps, modified in place.
        original_step_id: The FOR_EACH step's id (e.g. ``"step_2"``).
        expanded_step_ids: Its items' ids, in item order.
    """
    if not expanded_step_ids:
        logger.debug("for_each_aggregation_skipped_empty", original_step_id=original_step_id)
        return
    items = [
        (item_id, completed_steps[item_id])
        for item_id in expanded_step_ids
        if item_id in completed_steps
    ]
    if not items:
        logger.warning(
            "for_each_aggregation_no_results",
            original_step_id=original_step_id,
            expanded_step_ids=expanded_step_ids,
        )
        return
    failed = [(item_id, result) for item_id, result in items if result.get(FIELD_SUCCESS) is False]
    succeeded = [result for _, result in items if result.get(FIELD_SUCCESS) is not False]

    aggregated = _merge_item_results(succeeded) if succeeded else _all_failed(failed[0][1])
    if failed:
        aggregated[FIELD_FOR_EACH_FAILED_ITEMS] = [
            _failed_item(item_id, result) for item_id, result in failed
        ]
    # The readers that list failures skip the aggregate by this marker: its
    # items are listed one by one, and an all-failed aggregate is not one more.
    aggregated[FIELD_FOR_EACH_AGGREGATE] = True
    completed_steps[original_step_id] = aggregated

    logger.info(
        "for_each_results_aggregated",
        original_step_id=original_step_id,
        expanded_count=len(expanded_step_ids),
        succeeded_count=len(succeeded),
        failed_count=len(failed),
        aggregated_keys=list(aggregated.keys()),
    )


def _merge_item_results(results: list[dict[str, object]]) -> dict[str, object]:
    """Merge successful items: lists concatenated, confirmations collected, else the last.

    A key whose every value is a list concatenates them. ``result`` keeps every
    confirmation (a list when there are several — one reminder per item must
    reach the answer, not only the last one). Any other key keeps its last
    non-None value.

    Args:
        results: The successful items' entries, in item order.

    Returns:
        The merged entry.
    """
    merged: dict[str, object] = {}
    for key in dict.fromkeys(key for result in results for key in result):
        value = _merged_value(key, [result[key] for result in results if key in result])
        if value is not None:
            merged[key] = value
    return merged


def _merged_value(key: str, values: list[object]) -> object:
    """One key's merged value across the successful items (see ``_merge_item_results``).

    Args:
        key: The key being merged.
        values: Its value in each item that carries it, in item order.

    Returns:
        The concatenated lists, the confirmation(s), or the last non-None value;
        None when every value was None (the key is then left out).
    """
    lists = [value for value in values if isinstance(value, list)]
    if len(lists) == len(values):
        return [element for value in lists for element in value]
    present = [value for value in values if value is not None]
    if not present:
        return None
    if key == FIELD_RESULT and all(isinstance(value, str) for value in present):
        return present if len(present) > 1 else present[0]
    return present[-1]


def _all_failed(first: dict[str, object]) -> dict[str, object]:
    """The aggregate of a loop whose every item failed: the first failure's verdict.

    Args:
        first: The first failed item's entry.

    Returns:
        A failure entry, its words and code taken from that item.
    """
    return {
        FIELD_SUCCESS: False,
        FIELD_ERROR: first.get(FIELD_ERROR),
        FIELD_ERROR_CODE: first.get(FIELD_ERROR_CODE),
    }


def _failed_item(item_id: str, result: dict[str, object]) -> dict[str, object]:
    """One failed item as the aggregate carries it.

    Args:
        item_id: The item's step id (e.g. ``"step_2_item_1"``).
        result: Its stored entry.

    Returns:
        Its id, its error and its code.
    """
    return {
        FIELD_STEP_ID: item_id,
        FIELD_ERROR: result.get(FIELD_ERROR),
        FIELD_ERROR_CODE: result.get(FIELD_ERROR_CODE),
    }
