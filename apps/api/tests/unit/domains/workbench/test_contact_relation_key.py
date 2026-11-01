"""« See the relationship »: the same fold on both sides, computed once (ADR-369, Task 7.2).

A contact opens its relationship only when its name folds EXACTLY to a known
relation's — and folding identity has ONE implementation (`fold_name`), so the
backend publishes the folded key beside both names and the page compares two
keys it never computes itself.
"""

from __future__ import annotations

import pytest

from src.domains.relations.schemas import RelationSummary
from src.domains.shared.text_normalization import fold_name
from src.domains.workbench.schemas.contacts import Contact

pytestmark = pytest.mark.unit


def test_a_contact_and_a_relation_publish_the_same_folded_key() -> None:
    contact = Contact(
        id="people/c1",
        name="Élodie Martin",
        email=None,
        phone=None,
        organization=None,
        emails=[],
        phones=[],
        addresses=[],
        notes=None,
    )
    relation = RelationSummary(
        display_name="elodie martin",
        identity_confidence="exact",
        open_loops_count=0,
        calls_count=0,
    )

    assert contact.model_dump()["name_key"] == fold_name("Élodie Martin")
    assert relation.model_dump()["name_key"] == contact.model_dump()["name_key"]
