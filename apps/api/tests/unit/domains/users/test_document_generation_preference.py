"""User opt-in for document generation: model default, schema plumbing, GDPR map (ADR-226)."""

import pytest

from src.core.constants import DOCUMENT_GENERATION_ENABLED_DEFAULT
from src.domains.users.schemas import UserProfile, UserUpdate
from src.domains.users.user_data_map import USER_COLUMNS, UserColumnClass


@pytest.mark.unit
class TestDocumentGenerationPreference:
    """The per-user opt-in column is declared, plumbed and GDPR-classified."""

    def test_model_column_declared(self) -> None:
        from src.domains.users.models import User

        col = User.__table__.columns["document_generation_enabled"]
        assert col.nullable is False
        assert col.server_default is not None

    def test_update_schema_accepts_flag(self) -> None:
        upd = UserUpdate(document_generation_enabled=False)
        assert upd.document_generation_enabled is False
        # Omitted -> None (partial update semantics).
        assert UserUpdate().document_generation_enabled is None

    def test_profile_schema_default_matches_constant(self) -> None:
        field = UserProfile.model_fields["document_generation_enabled"]
        assert field.default is DOCUMENT_GENERATION_ENABLED_DEFAULT

    def test_gdpr_map_classifies_as_preference(self) -> None:
        assert USER_COLUMNS["document_generation_enabled"] is (UserColumnClass.RETAINED_PREFERENCE)
