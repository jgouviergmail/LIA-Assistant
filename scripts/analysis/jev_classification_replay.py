"""DEV-only fictional replay through LIA's native runtime and real accounting.

Dry-run is the default. --live requires an explicit active account, a small
budget and a new output file. No setting, model override or credential changes.
Pass the preceding report to carry the SAME total budget into another split.
"""

import argparse
import asyncio
import hashlib
import sys
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from tests.fixtures.classification_corpus import ReplayReport

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))


async def replay(args: argparse.Namespace) -> None:
    from sqlalchemy import select

    from src.core.config import settings
    from src.core.constants import JEV_CLASSIFICATION_MAX_ITEMS
    from src.domains.agents.services.qualification.batches import (
        ClassificationBatch,
        build_batches,
    )
    from src.domains.agents.services.qualification.policy import classify_answers
    from src.domains.agents.services.qualification.service import policy_fingerprint
    from src.domains.llm_config.jev_registry import JevUsage
    from src.domains.llm_config.jev_settings import (
        JevSnapshot,
        read_configuration,
        read_flags,
    )
    from src.domains.users.models import User
    from src.infrastructure.cache.pricing_cache import (
        PricingCacheService,
        get_cached_usd_eur_rate,
    )
    from src.infrastructure.cache.redis import get_redis_cache
    from src.infrastructure.database import get_db_context
    from src.infrastructure.database.registry import import_all_models
    from src.infrastructure.llm.jev_runtime import choose_many_with_jev
    from src.infrastructure.llm.typesafe_client import (
        MAX_REQUEST_BYTES,
        MAX_RESPONSE_BYTES,
    )
    from src.infrastructure.proactive.tracking import out_of_turn_spend
    from tests.fixtures.classification_corpus import (
        Corpus,
        ReplayCall,
        ReplayReport,
        score,
    )

    if settings.environment != "development":
        raise ValueError("This replay is restricted to a development instance")
    if not Decimal(0) < args.max_eur <= Decimal(".05"):
        raise ValueError("The total replay budget must be positive and at most EUR 0.05")
    if args.output.exists():
        raise ValueError("Choose a new report path; an earlier paid result must not be overwritten")
    corpus_path = ROOT / "apps/api/tests/fixtures" / f"jev_classification_{args.split}.json"
    corpus = Corpus.read(corpus_path)
    if not 1 <= len(corpus.items) <= 100:
        raise ValueError("The replay requires a bounded fictional fixture")
    prior = Decimal(0)
    if args.previous_report:
        prior = ReplayReport.model_validate_json(args.previous_report.read_bytes()).total_cost_eur
    if not prior.is_finite() or prior < 0 or prior >= args.max_eur:
        raise ValueError("No authorized budget remains")
    import_all_models()
    usages = {
        "email": JevUsage.EMAIL_CLASSIFICATION,
        "event": JevUsage.EVENT_CLASSIFICATION,
    }
    async with get_db_context() as db:
        flags_before = await read_flags(db)
        configs = {}
        for kind, usage in usages.items():
            readiness, config = await read_configuration(db, usage)
            if readiness != "ready" or config is None:
                raise ValueError(f"Native {kind} classification configuration is unavailable")
            configs[kind] = config
        owner = None
        if args.user_id:
            owner = await db.scalar(
                select(User.id).where(
                    User.id == args.user_id,
                    User.is_active.is_(True),
                    User.deleted_at.is_(None),
                )
            )
        if args.live and owner is None:
            raise ValueError("A live replay needs --user-id naming the active account to charge")
    if not await PricingCacheService(await get_redis_cache()).load_from_redis():
        raise ValueError("The DEV pricing/FX cache must be available before a replay")
    rate = Decimal(str(get_cached_usd_eur_rate()))
    queue: list[tuple[str, ClassificationBatch]] = []
    for kind in usages:
        remaining = [case.observation() for case in corpus.items if case.kind == kind]
        while remaining:
            batches = build_batches(
                remaining[:JEV_CLASSIFICATION_MAX_ITEMS],
                model=configs[kind].model,
                now=corpus.reference_time,
                timezone=corpus.timezone,
            )
            if not batches:
                raise ValueError("A whole fictional observation cannot fit the shipped budgets")
            queue.extend((kind, batch) for batch in batches)
            submitted = {value.identity for batch in batches for value in batch.members}
            remaining = [value for value in remaining if value.identity not in submitted]
    if len(queue) > 32:
        raise ValueError("Replay exceeds the native-call ceiling")
    report = ReplayReport(
        split=args.split,
        live=args.live,
        policy_sha256=policy_fingerprint(),
        corpus_sha256=hashlib.sha256(corpus_path.read_bytes()).hexdigest(),
        native_calls_planned=len(queue),
        request_bytes=sum(batch.request_bytes for _, batch in queue),
        estimated_input_tokens=sum(batch.estimated_input_tokens for _, batch in queue),
        budget_eur=args.max_eur,
        prior_cost_eur=prior,
        total_cost_eur=prior,
        models={kind: config.model for kind, config in configs.items()},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.touch(exist_ok=False)
    _save_report(report, args.output)
    predictions = {}
    spent = prior
    if args.live:
        if owner is None:
            raise ValueError("Missing accounting owner")
        run_id = f"classification-replay-{uuid4()}"
        report.run_id = run_id
        try:
            async with out_of_turn_spend(run_id, owner, "jev_decision"):
                for kind, batch in queue:
                    config = configs[kind]
                    # Reserve conservatively before sending; charge only returned
                    # counters via the ordinary runtime. No automatic retry.
                    reserve = (
                        (
                            Decimal(MAX_REQUEST_BYTES * 2) * config.price.input_price
                            + Decimal(MAX_RESPONSE_BYTES) * config.price.output_price
                        )
                        / 1_000_000
                        * rate
                    )
                    if spent + reserve > args.max_eur:
                        report.stop_reason = "budget_reservation"
                        break
                    started = perf_counter()
                    attempt = await choose_many_with_jev(
                        usage=usages[kind],
                        user_id=owner,
                        run_id=run_id,
                        state=batch.state,
                        questions=batch.questions,
                        snapshot=JevSnapshot(True, "ready", config),
                    )
                    if attempt.charge:
                        spent += Decimal(str(attempt.charge.cost_eur))
                    report.total_cost_eur = spent
                    report.calls.append(
                        ReplayCall(
                            kind=kind,
                            outcome=attempt.outcome,
                            latency_ms=(perf_counter() - started) * 1000,
                            charge=attempt.charge,
                            members=[value.identity for value in batch.members],
                            answers=attempt.answers,
                        )
                    )
                    _save_report(report, args.output)
                    if attempt.outcome != "success" or spent > args.max_eur:
                        report.stop_reason = "native_failure_or_budget"
                        break
                    for index, value in enumerate(batch.members):
                        predictions[value.identity] = classify_answers(
                            value,
                            category=attempt.answers.get(f"i{index}_category"),
                            priority=attempt.answers.get(f"i{index}_priority"),
                            now=corpus.reference_time,
                        )
        finally:
            report.quality = score(corpus, predictions)
            report.predictions = predictions
            async with get_db_context() as db:
                report.settings_unchanged = (await read_flags(db)) == flags_before
            _save_report(report, args.output)
    else:
        _save_report(report, args.output)
    print(report.model_dump_json(exclude={"calls", "predictions", "quality"}))
    if args.live and not score(corpus, predictions).passed:
        raise SystemExit("The semantic quality gate did not pass; keep both usages disabled")


def _save_report(report: ReplayReport, path: Path) -> None:
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--user-id", type=UUID)
    parser.add_argument("--split", choices=("cases", "holdout"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--previous-report", type=Path)
    parser.add_argument("--max-eur", type=Decimal, default=Decimal(".05"))
    asyncio.run(replay(parser.parse_args()))
