"""A graph config's run id is read where the orchestration service writes it."""

from __future__ import annotations

import pytest

from src.core.run_config import run_id_of
from src.domains.agents.services.planner.planner_utils import smart_plan_id

pytestmark = [pytest.mark.unit]


class TestRunIdOf:
    def test_reads_the_metadata_plane(self) -> None:
        assert run_id_of({"configurable": {"thread_id": "t"}, "metadata": {"run_id": "r"}}) == "r"

    def test_configurable_carries_no_run_id(self) -> None:
        """ADR-231: nobody writes it there, so nobody reads it there."""
        assert run_id_of({"configurable": {"run_id": "stale"}, "metadata": {}}) == ""

    @pytest.mark.parametrize("config", [None, "config", {}, {"metadata": None}, {"metadata": {}}])
    def test_anything_else_carries_no_run(self, config: object) -> None:
        assert run_id_of(config) == ""


class TestSmartPlanId:
    def test_a_plan_is_named_after_its_run(self) -> None:
        """Every plan used to be ``smart_unknown``."""
        assert smart_plan_id({"metadata": {"run_id": "run-7"}}) == "smart_run-7"

    def test_a_config_without_a_run_says_so(self) -> None:
        assert smart_plan_id({"configurable": {}}) == "smart_unknown"
