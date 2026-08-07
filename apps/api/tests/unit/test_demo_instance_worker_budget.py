"""The demonstrator's memory ceiling must fit the workers it actually runs.

Measured on the public instance, 2026-08-07: the API container reached
**1.985 GiB of its 2 GiB limit in thirteen minutes**, from cold, with almost no
traffic. Not a leak — arithmetic. It ran four uvicorn workers at roughly
480 MB each inside a ceiling sized for far fewer, because it reuses the
production image (``--workers 4`` in its ``CMD``) without the production
ceiling (8 GB). The next step up is the OOM killer, mid-demonstration.

Two numbers written in two files, each defensible alone and incoherent
together. So the invariant is stated once, here, over both:

    mem_limit >= workers * PER_WORKER_MB + BASE_MB

``PER_WORKER_MB`` is measured, not guessed, and ``BASE_MB`` covers what the
container holds outside the workers (interpreter, buffers, the tmpfs of /tmp).
A change to either side that breaks the relation fails here rather than at
02:00 in front of a visitor.
"""

from __future__ import annotations

import re

import pytest

from tests._repo_paths import repo_root_or_skip

pytestmark = pytest.mark.unit

ROOT = repo_root_or_skip()
ENVELOPE = ROOT / "docker-compose.demo-instance.yml"
TEMPLATES = (
    ROOT / ".env.demo-instance.example",
    ROOT / ".env.demo-instance.prod.example",
)

#: Resident set of ONE uvicorn worker of this application, measured on the
#: production host (four workers, 1.985 GiB total, minus the base below).
#: Rounded UP: a ceiling computed from an optimistic figure is not a ceiling.
PER_WORKER_MB = 512

#: What the container holds regardless of the worker count.
BASE_MB = 256


def _api_mem_limit_mb() -> int:
    """The ``mem_limit`` of the demonstrator's API service, in MB."""
    text = ENVELOPE.read_text(encoding="utf-8")
    service = re.search(r"^  demo-instance-api:\n(.*?)(?=^  [a-z])", text, re.M | re.S)
    assert service, "the demo-instance-api service disappeared from the envelope"
    limit = re.search(r"^\s+mem_limit:\s*(\d+)([gGmM])", service.group(1), re.M)
    assert limit, "demo-instance-api declares no mem_limit — an unbounded API on a shared host"
    value = int(limit.group(1))
    return value * 1024 if limit.group(2).lower() == "g" else value


def _declared_workers(template) -> int:
    match = re.search(r"^WEB_CONCURRENCY=(\d+)", template.read_text(encoding="utf-8"), re.M)
    assert match, f"{template.name} declares no WEB_CONCURRENCY"
    return int(match.group(1))


class TestTheCeilingFitsTheWorkers:
    @pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.suffixes[-2])
    def test_the_limit_covers_every_worker_it_asks_for(self, template) -> None:
        workers = _declared_workers(template)
        needed = workers * PER_WORKER_MB + BASE_MB

        limit = _api_mem_limit_mb()

        assert limit >= needed, (
            f"{template.name} asks for {workers} workers "
            f"({needed} MB needed at {PER_WORKER_MB} MB each plus {BASE_MB} MB base) "
            f"but the envelope caps the API at {limit} MB. Raise the ceiling or "
            "lower the worker count — the instance reached 99.24 % of a 2 GB cap "
            "in thirteen minutes with four workers."
        )

    def test_the_two_templates_ask_for_the_same_thing(self) -> None:
        """Local and production must be dimensioned alike, or one is untested."""
        counts = {t.name: _declared_workers(t) for t in TEMPLATES}

        assert len(set(counts.values())) == 1, (
            f"{counts} — the shape validated locally is not the shape that runs "
            "in production, so the local run proves nothing about the ceiling"
        )

    def test_the_ceiling_is_not_extravagant(self) -> None:
        """A cap is also a protection for the machine it shares.

        The demonstrator sits next to the production stack on one 16 GB host.
        Room to breathe is the point; room to swallow the host is not.
        """
        workers = _declared_workers(TEMPLATES[-1])

        limit = _api_mem_limit_mb()

        assert limit <= workers * PER_WORKER_MB + BASE_MB + 2048, (
            f"the API may take {limit} MB for {workers} workers — that is no "
            "longer a ceiling, and the production stack shares this machine"
        )


class TestTheWorkerCountThatRunsIsTheOneDeclared:
    """A setting the process ignores is a setting that lies to every reader.

    ``Dockerfile.prod`` pinned ``--workers 4`` in its ``CMD``, and an explicit
    flag beats the ``WEB_CONCURRENCY`` environment variable uvicorn would
    otherwise honour. Measured 2026-08-07 inside the running demonstrator::

        WEB_CONCURRENCY  = 2
        uvicorn ... --workers 4

    Two consequences, and the second is worse than the memory:

    - the container ran twice the workers it was dimensioned for;
    - ``connection_budget`` computes the worst-case PostgreSQL burst from
      ``settings.web_concurrency`` (2), while four workers each opened their
      own pools. The production guard that must refuse to boot on an
      over-subscribed budget was validating a number nobody used — 4 x (10+5)
      + 4x8 + 4x4 = 108 against 95 usable, and it started anyway.
    """

    def test_the_image_does_not_pin_a_worker_count(self) -> None:
        dockerfile = (ROOT / "apps/api/Dockerfile.prod").read_text(encoding="utf-8")
        cmd = next(line for line in dockerfile.splitlines() if line.startswith("CMD ["))

        assert "--workers" not in cmd, (
            "an explicit --workers overrides WEB_CONCURRENCY, so the setting "
            "every other layer reads (the connection budget included) stops "
            "describing the process"
        )

    def test_the_image_still_defaults_to_the_production_sizing(self) -> None:
        """Removing the flag must not silently drop production to one worker."""
        dockerfile = (ROOT / "apps/api/Dockerfile.prod").read_text(encoding="utf-8")

        assert re.search(
            r"^ENV WEB_CONCURRENCY=\d+", dockerfile, re.M
        ), "with the flag gone, the image must carry the default itself"

    def test_the_default_matches_what_the_code_expects(self) -> None:
        """One number, two places: the image and the settings must agree."""
        dockerfile = (ROOT / "apps/api/Dockerfile.prod").read_text(encoding="utf-8")
        image_default = int(re.search(r"^ENV WEB_CONCURRENCY=(\d+)", dockerfile, re.M).group(1))

        from src.core.constants import WEB_CONCURRENCY_DEFAULT

        assert image_default == WEB_CONCURRENCY_DEFAULT, (
            f"the image starts {image_default} workers while the settings "
            f"default to {WEB_CONCURRENCY_DEFAULT}; the connection budget is "
            "computed from the latter"
        )

    def test_the_metrics_mode_follows_the_effective_count(self) -> None:
        """Prometheus multiprocess was keyed on the flag that just left.

        The entrypoint enabled it with ``case "$*" in *--workers*``. With the
        flag gone that test never matches, and production would silently fall
        back to per-worker metrics — four workers each reporting a quarter of
        the truth.
        """
        entrypoint = (ROOT / "apps/api/docker-entrypoint.sh").read_text(encoding="utf-8")

        assert "WEB_CONCURRENCY" in entrypoint, (
            "the multiprocess decision must read the effective worker count, "
            "not a command-line flag that no longer exists"
        )

    def test_a_single_worker_does_not_get_multiprocess_metrics(self) -> None:
        """Caught by running the decision, not by reading it.

        The first rewrite keyed on the mere PRESENCE of a worker count, so
        `WEB_CONCURRENCY=1` switched aggregation on — something the flag-based
        test never did, because production always passed 4. One worker needs no
        aggregation and the MultiProcessCollector path is not free. Verified in
        a shell: absent -> off, 1 -> off, 2/3/4 -> on.
        """
        entrypoint = (ROOT / "apps/api/docker-entrypoint.sh").read_text(encoding="utf-8")

        assert "-gt 1" in entrypoint, "the rule is 'several workers', not 'a worker count is set'"
