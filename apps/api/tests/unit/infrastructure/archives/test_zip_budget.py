"""Unit tests for the shared zip-bomb budget guard.

The guard existed once, private to the plugin importer, coupled to plugin
exceptions. The spreadsheet importer needs the exact same protection — an
``.xlsx`` is a zip — so the rule is extracted here rather than written a second
time: one implementation, one place to fix, one behaviour to reason about.

Measured on realistic content (2026-08-18): a 20 000-row workbook compresses at
about 20x. A crafted archive reaches several thousand, which is precisely what
the decompressed-size budget refuses.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from src.infrastructure.archives.zip_budget import (
    ZipBudgetExceeded,
    enforce_zip_budgets,
)


def _infos(sizes: list[int]) -> list[zipfile.ZipInfo]:
    """Build ZipInfo entries declaring the given uncompressed sizes.

    Deflate is explicit: the default ``ZIP_STORED`` would make the compressed
    and declared sizes equal, and the point of the guard is precisely that they
    are not.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for index, size in enumerate(sizes):
            zf.writestr(f"member_{index}.bin", b"x" * size)
    with zipfile.ZipFile(io.BytesIO(buffer.getvalue())) as zf:
        return [info for info in zf.infolist() if not info.is_dir()]


@pytest.mark.unit
class TestEnforceZipBudgets:
    def test_an_archive_within_budget_passes(self) -> None:
        enforce_zip_budgets(_infos([100, 200]), max_files=10, max_decompressed_bytes=10_000)

    def test_too_many_members_is_refused(self) -> None:
        with pytest.raises(ZipBudgetExceeded) as excinfo:
            enforce_zip_budgets(_infos([10] * 5), max_files=3, max_decompressed_bytes=10_000)

        assert excinfo.value.reason == "too_many_files"
        assert excinfo.value.limit == 3
        assert excinfo.value.measured == 5

    def test_oversized_decompressed_content_is_refused(self) -> None:
        with pytest.raises(ZipBudgetExceeded) as excinfo:
            enforce_zip_budgets(_infos([1_000, 1_000]), max_files=10, max_decompressed_bytes=1_500)

        assert excinfo.value.reason == "decompressed_too_large"
        assert excinfo.value.limit == 1_500
        assert excinfo.value.measured == 2_000

    def test_the_declared_size_is_used_not_the_compressed_one(self) -> None:
        """A zip bomb is small on disk and huge once expanded — the budget must
        read the declared uncompressed size, which is what the guard exists for."""
        infos = _infos([50_000])
        assert infos[0].compress_size < infos[0].file_size

        with pytest.raises(ZipBudgetExceeded) as excinfo:
            enforce_zip_budgets(infos, max_files=10, max_decompressed_bytes=10_000)

        assert excinfo.value.measured == 50_000

    def test_exactly_at_the_limit_is_allowed(self) -> None:
        enforce_zip_budgets(_infos([500, 500]), max_files=2, max_decompressed_bytes=1_000)

    def test_an_empty_archive_passes(self) -> None:
        enforce_zip_budgets([], max_files=1, max_decompressed_bytes=1)

    def test_the_error_message_states_both_numbers(self) -> None:
        """The message reaches an operator: it must say the limit and the measure."""
        with pytest.raises(ZipBudgetExceeded) as excinfo:
            enforce_zip_budgets(_infos([10] * 4), max_files=2, max_decompressed_bytes=10_000)

        message = str(excinfo.value)
        assert "2" in message and "4" in message

    def test_it_is_a_value_error_so_existing_handlers_keep_working(self) -> None:
        assert issubclass(ZipBudgetExceeded, ValueError)
