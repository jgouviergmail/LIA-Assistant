"""Opt-in bounded replay of the shipped meeting selector on synthetic labelled cases.

Run with the backend interpreter from apps/api. TYPESAFE_API_KEY is read only
from the process environment. No LIA account, database or real transcript is used.
The output records actual paid usage; the credential never enters the report.
"""

import argparse
import asyncio
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path
from time import perf_counter
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
load_dotenv(ROOT / ".env")


async def replay(args: argparse.Namespace) -> None:
    # The backend path and settings must be bootstrapped before these imports.
    from src.domains.meetings import (
        jev_selection,
    )
    from src.domains.meetings.template_catalogue import (
        BUILTIN_TEMPLATES,
    )
    from src.domains.meetings.template_service import (
        MeetingTemplateService,
    )
    from src.infrastructure.llm.decision_types import (
        DecisionAttempt,
        DecisionCharge,
    )
    from src.infrastructure.llm.typesafe_client import (
        TypeSafeClient,
        TypeSafeError,
    )

    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    if not 1 <= len(cases) <= 100:
        raise ValueError("Replay bound is 100 synthetic cases")
    key = os.environ["TYPESAFE_API_KEY"]
    rows = []
    owner = uuid4()
    # Builtin resolution uses the real catalogue and performs no SQL.
    service = MeetingTemplateService(AsyncMock())
    for index, case in enumerate(cases):
        candidates = [
            await service.resolve(owner, f"builtin:{item.key}", case["language"])
            for item in BUILTIN_TEMPLATES
            if item.auto_selectable
        ]
        native = {}

        async def call(**kwargs):
            start = perf_counter()
            try:
                async with httpx.AsyncClient() as http:
                    result = await TypeSafeClient(http, key).choose(
                        model="jev-1.13.0",
                        state=kwargs["state"],
                        question=kwargs["question"],
                        timeout_seconds=2,
                    )
                cost = result.usage.input_tokens * 0.042 / 1_000_000
                native.update(
                    confidence=result.answer.confidence,
                    input_tokens=result.usage.input_tokens,
                    output_tokens=result.usage.output_tokens,
                    cost_usd=cost,
                )
                return DecisionAttempt(
                    result.answer,
                    DecisionCharge(
                        model=result.model,
                        input_tokens=result.usage.input_tokens,
                        output_tokens=result.usage.output_tokens,
                        cost_usd=cost,
                        cost_eur=cost,
                    ),
                    "success",
                )
            except TypeSafeError as exc:
                native.update(error=exc.code, status_code=exc.status_code)
                if exc.usage:
                    native.update(
                        input_tokens=exc.usage.input_tokens,
                        output_tokens=exc.usage.output_tokens,
                        cost_usd=exc.usage.input_tokens * 0.042 / 1_000_000,
                    )
                return DecisionAttempt(outcome=exc.code)
            finally:
                native["provider_path_ms"] = round((perf_counter() - start) * 1000, 2)

        with patch.object(jev_selection, "choose_with_jev", call), patch.object(
            jev_selection, "record_selection_charge", AsyncMock()
        ):
            selected = await jev_selection.select_template_with_jev(
                meeting_id=uuid4(),
                user_id=owner,
                run_id=f"synthetic-{index}",
                candidates=candidates,
                excerpt=case["transcript"],
                calendar_title=case.get("title"),
            )
        prediction = (
            str(selected.template.ref).removeprefix("builtin:")
            if selected.template
            else None
        )
        rows.append(
            {
                "id": case["id"],
                "language": case["language"],
                "expected": case["expected"],
                "selected": prediction,
                "accepted": prediction is not None,
                "wrong_acceptance": prediction is not None
                and prediction not in case["expected"],
                **native,
            }
        )
    timings = sorted(row["provider_path_ms"] for row in rows)
    report = {
        "prompt_sha256": hashlib.sha256(
            jev_selection.load_meeting_prompt("meeting_jev_selection_prompt").encode()
        ).hexdigest(),
        "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "cases": len(rows),
        "accepted": sum(row["accepted"] for row in rows),
        "wrong_acceptances": sum(row["wrong_acceptance"] for row in rows),
        "median_ms": statistics.median(timings),
        "max_ms": max(timings),
        "cost_usd": sum(row.get("cost_usd", 0) for row in rows),
        "results": rows,
    }
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "results"}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Explicitly permit paid TypeSafe calls",
    )
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(replay(parser.parse_args()))
