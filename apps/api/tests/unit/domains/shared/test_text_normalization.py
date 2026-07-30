"""Name-folding chokepoint tests (hoisted from relations — peers program, Lot 1)."""

import pytest

from src.domains.shared.text_normalization import fold_name


@pytest.mark.unit
class TestFoldName:
    """fold_name is the single identity-folding chokepoint (relations + peers)."""

    def test_strips_accents_and_case(self):
        assert fold_name("Jérôme GOUVIER") == "jerome gouvier"

    def test_handles_empty_and_whitespace(self):
        assert fold_name("") == ""
        assert fold_name("   ") == ""

    def test_is_idempotent(self):
        once = fold_name("Måns Öberg")
        assert fold_name(once) == once

    def test_preserves_inner_whitespace_shape(self):
        # Only leading/trailing whitespace is stripped; inner spacing is kept
        # (exact-match semantics — "Jean  Dupont" is not "Jean Dupont").
        assert fold_name("  Ana María  ") == "ana maria"
        assert fold_name("Jean  Dupont") == "jean  dupont"
