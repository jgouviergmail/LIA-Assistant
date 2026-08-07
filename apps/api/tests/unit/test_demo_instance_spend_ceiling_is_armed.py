"""The demonstrator's spend ceiling must be able to SEE the spend.

``INSTANCE_DAILY_BUDGET_EUR`` (ADR-216) is the owner's stated financial
protection — one euro a day, first come first served. It reads a ledger fed by
the pricing catalogue, so it is only a ceiling while the model the instance
runs on has an ACTIVE price in the database it runs against.

Measured on the running instance, 2026-08-07: five real messages burned
59 344 tokens and the ledger recorded 0,000025 EUR, because every LLM type was
pointed at ``deepseek-v4-flash``, a model this database's catalogue does not
carry. ``pricing_cache_fallback_total{reason="model_not_found"}`` stood at 88.
One euro of ledger would have been roughly four hundred euros of invoice.

Why the catalogue was incomplete, and what it took to fix: the SEEDS are the
maintained source of truth for the model catalogue; the migrations carry an
older, partial copy. The demonstrator ran on the partial one because the seed
bundle could not be applied — and neither could ANY installation, which is the
larger defect this uncovered:

1. the gate vetoed on "is the personalities table empty?", but the migrations
   insert fourteen rows unconditionally just above it, so the answer was never
   yes ("personalities already holds 14 row(s) — SQL seeds SKIPPED");
2. once that was corrected to the question the gate always claimed to ask —
   has anyone CHOSEN a personality? — the wrapper died on `missing seed file
   google_api_pricing_seed.sql`: the API image is built from `apps/api` and
   carries no `infrastructure/`, so the files arrive by mount, and the
   demonstrator's envelope had none.

With both fixed the bundle applies: 102 models / 91 prices became 122 / 224,
and the configured model is priced. Two invariants therefore hold together —
the envelope must ASK for the bundle, and the configured model must be one the
resulting catalogue prices. ``unbillable_model`` enforces the second against
the real database and provisioning refuses.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
COMPOSE = ROOT / "docker-compose.demo-instance.yml"
TASKFILE = ROOT / "Taskfile.yml"
ENV_TEMPLATE = ROOT / ".env.demo-instance.example"


def _env_value(key: str) -> str | None:
    """Value of ``key`` in the demonstrator template, if declared."""
    for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return None


class TestTheEnvelopeAsksForTheMaintainedCatalogue:
    def test_it_applies_the_reference_seed_bundle(self) -> None:
        """The seeds are what is maintained; the migrations are a partial copy.

        Running on the migrations alone is how the daily ceiling went blind:
        91 prices instead of 224, and the configured model among the missing.
        """
        assert "APPLY_SEEDS=true" in COMPOSE.read_text(encoding="utf-8"), (
            "the demonstrator's database is recreated empty at every boot and "
            "must be re-seeded each time, or its pricing catalogue is partial "
            "and INSTANCE_DAILY_BUDGET_EUR reads zero whatever is spent"
        )

    def test_the_digest_is_computed_not_typed(self) -> None:
        body = TASKFILE.read_text(encoding="utf-8")

        # A 64-hex literal would be correct exactly until somebody edits a
        # seed, and the wrapper would then refuse the whole bundle.
        assert "compute_seed_bundle_sha256" in body, (
            "the demonstrator's seed digest must be recomputed from the "
            "repository, like the installer does"
        )

    def test_every_demonstrator_start_carries_the_digest(self) -> None:
        body = TASKFILE.read_text(encoding="utf-8")
        start_tasks = re.findall(
            r"^  (demo:up(?::[a-z]+)?):\n(.*?)(?=^  [a-z][\w:]*:\n)",
            body,
            re.MULTILINE | re.DOTALL,
        )

        assert {name for name, _ in start_tasks} == {
            "demo:up",
            "demo:up:dev",
            "demo:up:tunnel",
        }, "a new way to start the demonstrator must carry the digest too"
        for name, block in start_tasks:
            assert "SEED_BUNDLE_SHA256" in block, (
                f"{name} starts the envelope without the seed digest, so the "
                "entrypoint refuses to seed and the ceiling goes blind"
            )

    def test_the_envelope_says_which_catalogue_it_runs_on(self) -> None:
        # The next reader must not have to rediscover why this matters.
        assert "unbillable_model" in COMPOSE.read_text(encoding="utf-8")


class TestTheCeilingIsCheckedAgainstTheRealCatalogue:
    def test_provisioning_is_the_enforcement_point(self) -> None:
        """`task demo:start` provisions, so every start re-checks the money."""
        body = TASKFILE.read_text(encoding="utf-8")
        start = re.search(r"^  demo:start:\n(.*?)(?=^  [a-z][\w:]*:\n)", body, re.M | re.S)

        assert start and "demo:provision" in start.group(1), (
            "starting the demonstrator must run the provisioning that refuses "
            "a model this database cannot price"
        )

    def test_an_operator_can_ask_a_running_instance_whether_the_money_is_armed(
        self,
    ) -> None:
        """A ceiling nobody can interrogate is a ceiling nobody trusts.

        `task demo:verify` already answers "is the closed surface closed";
        this makes it answer "and can the ledger see what we spend".
        """
        body = TASKFILE.read_text(encoding="utf-8")
        verify = re.search(r"^  demo:verify:\n(.*?)(?=^  [a-z][\w:]*:\n)", body, re.M | re.S)

        assert verify, "demo:verify disappeared"
        assert "--verify" in verify.group(1), (
            "demo:verify must also ask the instance whether its configured "
            "model is priced — the surface and the money are both protections"
        )


class TestTheTemplateStatesWhatItDependsOn:
    def test_it_names_the_model_every_llm_type_is_pointed_at(self) -> None:
        assert _env_value("DEMO_INSTANCE_LLM_MODEL")
        assert _env_value("DEMO_INSTANCE_LLM_PROVIDER")

    def test_it_still_declares_the_ceiling_that_model_feeds(self) -> None:
        assert _env_value("INSTANCE_DAILY_BUDGET_EUR")

    def test_it_warns_that_the_model_must_be_priced(self) -> None:
        """The one thing a copy-paste operator must not get wrong."""
        template = ENV_TEMPLATE.read_text(encoding="utf-8")
        assert "price" in template.lower()
