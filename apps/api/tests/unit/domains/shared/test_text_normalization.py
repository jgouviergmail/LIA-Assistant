"""Identity-folding chokepoint tests (relations + peers).

Two folds, two rules — and the difference is load-bearing: a NAME is folded
aggressively (accents dropped, casefold) because two spellings of a person are
the same person; an ADDRESS is folded conservatively (strip + ASCII lower)
because two spellings of a mailbox are NOT necessarily the same mailbox.
"""

import pytest

from src.domains.shared.text_normalization import fold_email, fold_name


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


@pytest.mark.unit
class TestFoldEmail:
    """fold_email is the single ADDRESS-folding chokepoint (peers discovery).

    Deliberately weaker than :func:`fold_name`: an address identifies a
    mailbox, not a person, so folding may only remove differences no mail
    system can distinguish.
    """

    def test_case_and_surrounding_whitespace_are_not_a_difference(self):
        assert fold_email("  Jean.Dupont@Gmail.COM ") == "jean.dupont@gmail.com"

    def test_is_idempotent(self):
        once = fold_email(" Jean@Example.ORG ")
        assert fold_email(once) == once

    def test_handles_empty_and_whitespace(self):
        assert fold_email("") == ""
        assert fold_email("   ") == ""

    def test_never_folds_accents_away(self):
        """The name fold would merge these; the address fold must not.

        ``jerome@x.com`` and ``jérôme@x.com`` are two different mailboxes —
        folding accents here would hand a searcher someone else's account.
        """
        assert fold_email("jérôme@x.com") != fold_email("jerome@x.com")

    def test_never_expands_the_sharp_s(self):
        """casefold() maps ß→ss — that would merge two distinct mailboxes."""
        assert fold_email("straße@x.com") != fold_email("strasse@x.com")
        assert fold_email("STRAẞE@x.com") == "straße@x.com"
