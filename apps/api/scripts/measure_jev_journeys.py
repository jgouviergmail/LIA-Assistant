"""Offline, read-only OFF/ON report from explicitly annotated journey samples.

Run from apps/api: python scripts/measure_jev_journeys.py --samples samples.json
No credentials, provider requests or changes to instance switches.
"""

import argparse
import json
from pathlib import Path

from pydantic import TypeAdapter

from src.infrastructure.observability.jev_journey_report import (
    JourneySample,
    compare_journeys,
    samples_from_logs,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--samples", type=Path, help="Reviewed, explicitly paired JSON samples")
    source.add_argument(
        "--logs", type=Path, help="Export delivery events; mode and quality stay unknown"
    )
    parser.add_argument(
        "--environment",
        help="Commit, config and dataset snapshot fingerprint",
    )
    args = parser.parse_args()
    output: object
    if args.logs:
        if not args.environment:
            parser.error("--logs requires --environment identifying the observed snapshot")
        with args.logs.open(encoding="utf-8") as lines:
            samples = samples_from_logs(lines, environment=args.environment)
        output = [sample.model_dump() for sample in samples]
    else:
        samples = TypeAdapter(list[JourneySample]).validate_json(args.samples.read_bytes())
        output = compare_journeys(samples)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
