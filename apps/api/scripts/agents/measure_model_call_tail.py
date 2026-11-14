"""Measure the tail of model calls and answer streams, from Prometheus (lot 26, read only).

A MEASUREMENT, never a gate, and free: it asks Prometheus, nothing else. A model stream
can stall — a provider that stops sending without closing — and LIA has no detector for
it beyond each slot's timeout. Before writing one, this reads what the metrics already
hold over a window: model calls and their errors by kind, how many took longer than 30
and 60 seconds and on which node, the answer streams and the longest of them, their
errors, the external timeouts, and the gaps between two answer tokens — how many, and
how many longer than 10 and 30 seconds (``sse_token_gap_seconds``). Counts only.

Run in the API container (production: through the read-only harness)::

    python -m scripts.agents.measure_model_call_tail --prometheus http://lia-prometheus-dev:9090
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from typing import Any, Final

#: Below this, an increase over the window is rounding, not an event.
NOISE: Final = 0.5


def queries(window: str) -> dict[str, str]:
    """The PromQL expressions, each over ``window`` (a Prometheus duration such as ``7d``)."""

    def over(seconds: str) -> str:
        return (
            f"sum by (node_name) (increase(llm_api_latency_seconds_count[{window}]))"
            f' - sum by (node_name) (increase(llm_api_latency_seconds_bucket{{le="{seconds}"}}'
            f"[{window}]))"
        )

    def gaps_over(seconds: str) -> str:
        return (
            f"sum(increase(sse_token_gap_seconds_count[{window}]))"
            f' - sum(increase(sse_token_gap_seconds_bucket{{le="{seconds}"}}[{window}]))'
        )

    return {
        "llm_calls": f"sum(increase(llm_api_calls_total[{window}]))",
        "llm_errors_by_type": f"sum by (error_type) (increase(llm_api_errors_total[{window}]))",
        "llm_latency_buckets": f"sum by (le) (increase(llm_api_latency_seconds_bucket[{window}]))",
        "llm_over_30s_by_node": over("30.0"),
        "llm_over_60s_by_node": over("60.0"),
        "sse_streams": f"sum(increase(sse_streaming_duration_seconds_count[{window}]))",
        "sse_over_120s": (
            f"sum(increase(sse_streaming_duration_seconds_count[{window}]))"
            f' - sum(increase(sse_streaming_duration_seconds_bucket{{le="120.0"}}[{window}]))'
        ),
        "sse_errors": (
            f"sum by (error_type, node_name) (increase(sse_streaming_errors_total[{window}]))"
        ),
        "external_timeouts": (
            f"sum by (service_name) (increase(external_service_timeouts_total[{window}]))"
        ),
        # The gap between two answer tokens of a stream a person waits for: a stall
        # is a long gap no timeout ends (sse_token_gap_seconds, lot 26 follow-up).
        "token_gaps": f"sum(increase(sse_token_gap_seconds_count[{window}]))",
        "token_gaps_over_10s": gaps_over("10.0"),
        "token_gaps_over_30s": gaps_over("30.0"),
        "token_gap_buckets": f"sum by (le) (increase(sse_token_gap_seconds_bucket[{window}]))",
    }


def readings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """The series of one answer above the noise, each with its labels and its value."""
    out: list[dict[str, Any]] = []
    for item in payload.get("data", {}).get("result", []):
        value = float(item["value"][1])
        if value >= NOISE:
            out.append({"labels": item.get("metric", {}), "value": round(value, 1)})
    return out


def _ask(prometheus: str, expression: str) -> dict[str, Any]:
    url = f"{prometheus.rstrip('/')}/api/v1/query?" + urllib.parse.urlencode({"query": expression})
    with urllib.request.urlopen(url, timeout=60) as response:  # noqa: S310 - operator's own URL
        answer: dict[str, Any] = json.loads(response.read())
    return answer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--prometheus", default="http://lia-prometheus-dev:9090")
    parser.add_argument("--window", default="7d", help="a Prometheus duration (default: 7d)")
    args = parser.parse_args(argv)
    result = {
        name: readings(_ask(args.prometheus, expression))
        for name, expression in queries(args.window).items()
    }
    json.dump(result, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
