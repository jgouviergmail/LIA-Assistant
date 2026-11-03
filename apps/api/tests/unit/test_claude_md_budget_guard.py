"""Guard: ``CLAUDE.md`` keeps to a stated budget, and a justified addition is never blocked.

Why
---
The file opens every session and is mirrored into ``AGENTS.md``, so each line costs
every session; the prose asking to keep additions short did not hold (one bullet
reached 12,415 characters). ``scripts/audit/claude_md_budget.py`` is the instrument.
These tests prove each transition on a synthetic repository, including the owner's
condition that lifting a limit takes one sentence and that the sentence is kept, then
read the real repository's verdict.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

from tests._repo_paths import repo_root_or_skip

REPO_ROOT = repo_root_or_skip()
AUDIT_DIR = REPO_ROOT / "scripts" / "audit"
SCRIPT_PATH = AUDIT_DIR / "claude_md_budget.py"

pytestmark = pytest.mark.unit

_MODULE_NAME = "_lia_audit_claude_md_budget"
_REASON = "the rule closes a defect class and has no ADR yet"


def _load() -> ModuleType:
    cached = sys.modules.get(_MODULE_NAME)
    if cached is not None:
        return cached
    # The script imports its sibling ``doc_audit`` by name, as it does when it runs
    # from scripts/audit/, where Python puts the script's directory first on the path.
    if str(AUDIT_DIR) not in sys.path:
        sys.path.insert(0, str(AUDIT_DIR))
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


budget = _load()


def _repo(tmp_path: Path, text: str, **overrides: object) -> Path:
    """A synthetic repository holding one ``CLAUDE.md`` and its baseline."""
    (tmp_path / "CLAUDE.md").write_text(text, encoding="utf-8", newline="\n")
    baseline = tmp_path / budget.BASELINE_REL
    baseline.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "block_max_chars": 50,
        "headroom_bytes": 10,
        "max_bytes": 1000,
        "raises": [],
        "long_blocks": [],
    } | overrides
    baseline.write_text(json.dumps(data), encoding="utf-8", newline="\n")
    return tmp_path


def _baseline(root: Path) -> dict:
    return json.loads((root / budget.BASELINE_REL).read_text(encoding="utf-8"))


class TestBlocks:
    """What counts as a block decides everything else."""

    def test_a_list_item_keeps_its_continuation_lines(self) -> None:
        blocks = budget.blocks_of("- first line\n  second line\n- other\n")

        assert [b.text for b in blocks] == ["- first line second line", "- other"]
        assert [b.line for b in blocks] == [1, 3]

    def test_a_paragraph_is_a_block(self) -> None:
        assert [b.text for b in budget.blocks_of("one\ntwo\n\nthree\n")] == [
            "one two",
            "three",
        ]

    def test_a_nested_or_numbered_item_is_its_own_block(self) -> None:
        blocks = budget.blocks_of("- parent\n  1. child\n  2. other\n")

        assert [b.text for b in blocks] == ["- parent", "1. child", "2. other"]

    def test_code_fences_tables_and_headings_are_not_blocks(self) -> None:
        text = "# title\n\n```bash\n- not an item\n```\n\n| a | b |\n|---|---|\n| c | d |\n"

        assert budget.blocks_of(text) == []

    def test_a_long_line_inside_a_fence_is_not_a_block(self, tmp_path: Path) -> None:
        text = "```\n" + "x" * 700 + "\n```\n"

        assert budget.check(_repo(tmp_path, text)).problems == ()

    def test_inline_code_opening_a_line_hides_no_block(self) -> None:
        """A line opening on ```inline``` is no fence: what follows stays a block."""
        blocks = budget.blocks_of("```quoted``` opens a line.\n\n- a rule\n")

        assert [b.text for b in blocks] == ["```quoted``` opens a line.", "- a rule"]

    def test_a_long_rule_after_inline_code_opening_a_line_fails(self, tmp_path: Path) -> None:
        text = "```quoted``` opens a line.\n\n- " + "x" * 700 + "\n"

        outcome = budget.check(_repo(tmp_path, text))

        assert len(outcome.problems) == 1 and "--allow" in outcome.problems[0]

    def test_a_long_rule_after_a_quoted_fence_fails(self, tmp_path: Path) -> None:
        text = "Quoted ``` fence.\n\n- " + "x" * 700 + "\n\n```\ncode\n```\n"

        outcome = budget.check(_repo(tmp_path, text))

        assert len(outcome.problems) == 1 and "--allow" in outcome.problems[0]


class TestCheck:
    """The limits, and what a problem tells the reader to do."""

    def test_a_file_within_budget_passes(self, tmp_path: Path) -> None:
        outcome = budget.check(_repo(tmp_path, "- short\n"))

        assert outcome.problems == ()
        assert outcome.size == len(b"- short\n")

    def test_over_the_ceiling_fails_and_names_the_way_out(self, tmp_path: Path) -> None:
        outcome = budget.check(_repo(tmp_path, "- short\n", max_bytes=3))

        assert len(outcome.problems) == 1
        assert "--raise" in outcome.problems[0]

    def test_a_long_block_fails_and_names_the_way_out(self, tmp_path: Path) -> None:
        outcome = budget.check(_repo(tmp_path, "- " + "x" * 60 + "\n"))

        assert len(outcome.problems) == 1
        assert "--allow" in outcome.problems[0]

    def test_a_block_at_the_cap_passes(self, tmp_path: Path) -> None:
        assert budget.check(_repo(tmp_path, "- " + "x" * 48 + "\n")).problems == ()

    def test_an_admitted_block_passes(self, tmp_path: Path) -> None:
        text = "- " + "x" * 60 + "\n"
        start = text.strip()[: budget.START_CHARS]
        entry = {"starts": start, "chars": 62, "reason": _REASON}

        assert budget.check(_repo(tmp_path, text, long_blocks=[entry])).problems == ()

    def test_an_admitted_block_may_not_grow(self, tmp_path: Path) -> None:
        text = "- " + "x" * 70 + "\n"
        start = text.strip()[: budget.START_CHARS]
        entry = {"starts": start, "chars": 62, "reason": _REASON}

        outcome = budget.check(_repo(tmp_path, text, long_blocks=[entry]))

        assert len(outcome.problems) == 1 and "grew" in outcome.problems[0]

    def test_an_entry_that_no_longer_applies_fails(self, tmp_path: Path) -> None:
        entry = {"starts": "- gone", "chars": 62, "reason": _REASON}

        outcome = budget.check(_repo(tmp_path, "- short\n", long_blocks=[entry]))

        assert len(outcome.problems) == 1 and "--update" in outcome.problems[0]


class TestDefaultWindow:
    """What a default Codex reads must reach the conduct and the principles."""

    def test_a_heading_inside_the_window_passes(self, tmp_path: Path) -> None:
        window = {"bytes": 100, "heading": "## Rules"}

        root = _repo(tmp_path, "- short\n\n## Rules\n", default_window=window)

        assert budget.check(root).problems == ()

    def test_a_heading_past_the_window_fails_and_names_the_repair(self, tmp_path: Path) -> None:
        window = {"bytes": 5, "heading": "## Rules"}

        outcome = budget.check(_repo(tmp_path, "- short\n\n## Rules\n", default_window=window))

        assert len(outcome.problems) == 1 and "Move it up" in outcome.problems[0]

    def test_a_heading_that_no_longer_exists_fails(self, tmp_path: Path) -> None:
        window = {"bytes": 100, "heading": "## Gone"}

        outcome = budget.check(_repo(tmp_path, "- short\n", default_window=window))

        assert len(outcome.problems) == 1 and "absent" in outcome.problems[0]

    def test_a_substring_of_a_longer_heading_is_not_the_heading(self, tmp_path: Path) -> None:
        window = {"bytes": 100, "heading": "## Rules"}

        outcome = budget.check(_repo(tmp_path, "- x\n### Rules of play\n", default_window=window))

        assert len(outcome.problems) == 1 and "absent" in outcome.problems[0]

    def test_no_window_declared_checks_nothing(self, tmp_path: Path) -> None:
        assert budget.check(_repo(tmp_path, "- short\n")).problems == ()


class TestUpdate:
    """The ratchet only tightens."""

    def test_it_lowers_the_ceiling_to_the_size_plus_headroom(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n")

        budget.update(root)

        assert _baseline(root)["max_bytes"] == len(b"- short\n") + 10

    def test_it_never_raises_the_ceiling(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n", max_bytes=3)

        budget.update(root)

        assert _baseline(root)["max_bytes"] == 3

    def test_it_removes_what_no_longer_applies_and_lowers_what_shrank(self, tmp_path: Path) -> None:
        text = "- " + "x" * 60 + "\n"
        start = text.strip()[: budget.START_CHARS]
        entries = [
            {"starts": start, "chars": 90, "reason": _REASON},
            {"starts": "- gone", "chars": 90, "reason": _REASON},
        ]
        root = _repo(tmp_path, text, long_blocks=entries)

        budget.update(root)

        assert _baseline(root)["long_blocks"] == [{"starts": start, "chars": 62, "reason": _REASON}]

    def test_it_never_admits_a_block(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- " + "x" * 60 + "\n")

        budget.update(root)

        assert _baseline(root)["long_blocks"] == []


class TestAJustifiedAdditionIsNeverBlocked:
    """Owner's condition: one command and one sentence, and the sentence stays."""

    def test_raising_lifts_the_ceiling_and_keeps_the_reason(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n", max_bytes=3)

        ceiling = budget.raise_ceiling(root, _REASON)

        data = _baseline(root)
        assert ceiling == data["max_bytes"] == len(b"- short\n") + 10
        assert budget.check(root).problems == ()
        assert data["raises"][0]["reason"] == _REASON
        assert (data["raises"][0]["from"], data["raises"][0]["to"]) == (3, ceiling)

    def test_raising_refuses_an_empty_reason(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="sentence"):
            budget.raise_ceiling(_repo(tmp_path, "- short\n", max_bytes=3), "because")

    def test_raising_refuses_when_there_is_nothing_to_raise(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="nothing to raise"):
            budget.raise_ceiling(_repo(tmp_path, "- short\n"), _REASON)

    def test_allowing_admits_the_block_and_keeps_the_reason(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- " + "x" * 60 + "\n")

        budget.allow_block(root, "- xxx", _REASON)

        assert budget.check(root).problems == ()
        assert _baseline(root)["long_blocks"][0]["reason"] == _REASON

    def test_allowing_a_block_again_records_its_new_length(self, tmp_path: Path) -> None:
        text = "- " + "x" * 70 + "\n"
        start = text.strip()[: budget.START_CHARS]
        entry = {"starts": start, "chars": 62, "reason": _REASON}
        root = _repo(tmp_path, text, long_blocks=[entry])

        budget.allow_block(root, "- xxx", _REASON + " and it grew")

        assert budget.check(root).problems == ()
        assert [e["chars"] for e in _baseline(root)["long_blocks"]] == [72]

    def test_allowing_refuses_an_empty_reason(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="sentence"):
            budget.allow_block(_repo(tmp_path, "- " + "x" * 60 + "\n"), "- xxx", "long")

    def test_allowing_refuses_a_start_that_names_no_single_block(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="expected one"):
            budget.allow_block(_repo(tmp_path, "- " + "x" * 60 + "\n"), "- nothing", _REASON)


class TestCommandLine:
    """The exit code is what `task lint:docs` reads."""

    def test_within_budget_exits_zero(self, tmp_path: Path) -> None:
        assert budget.main(["budget", str(_repo(tmp_path, "- short\n"))]) == 0

    def test_a_problem_exits_one(self, tmp_path: Path) -> None:
        assert budget.main(["budget", str(_repo(tmp_path, "- short\n", max_bytes=3))]) == 1

    def test_a_refused_reason_exits_two(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n", max_bytes=3)

        assert budget.main(["budget", str(root), "--raise", "no"]) == 2

    def test_update_tightens_through_the_command_line(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n")

        assert budget.main(["budget", str(root), "--update"]) == 0
        assert _baseline(root)["max_bytes"] == len(b"- short\n") + 10

    def test_raise_lifts_through_the_command_line(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- short\n", max_bytes=3)

        assert budget.main(["budget", str(root), "--raise", _REASON]) == 0
        assert budget.check(root).problems == ()

    def test_allow_admits_through_the_command_line(self, tmp_path: Path) -> None:
        root = _repo(tmp_path, "- " + "x" * 60 + "\n")

        assert budget.main(["budget", str(root), "--allow", "- xxx", _REASON]) == 0
        assert budget.check(root).problems == ()

    def test_a_console_code_page_never_ends_the_run(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A message quotes the file; cp1252 cannot encode an arrow, and that must not raise."""
        root = _repo(tmp_path, "- → " + "x" * 60 + "\n")
        console = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
        monkeypatch.setattr(sys, "stdout", console)
        monkeypatch.setattr(sys, "stderr", console)

        assert budget.main(["budget", str(root)]) == 1


def test_the_repository_keeps_to_its_budget() -> None:
    """The real verdict, so the guard reds with the file and not only with the task."""
    outcome = budget.check(REPO_ROOT)

    assert outcome.problems == (), "\n".join(outcome.problems)
