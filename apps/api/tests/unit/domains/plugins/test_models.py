"""Unit tests for the Agent Plugins persistence model (ADR-225).

DB-free mapper checks: the ``user_plugins`` table shape, and the nullable
``plugin_id`` provenance link added to ``skills`` and ``user_mcp_servers``.
``ON DELETE SET NULL`` is the deliberate safety net (a raw row deletion turns
plugin components back into ordinary manual ones instead of cascading data
away); the clean group uninstall is service-driven.
"""

from uuid import uuid4

import pytest
from sqlalchemy import inspect

from src.domains.plugins.models import UserPlugin
from src.domains.skills.models import Skill
from src.domains.user_mcp.models import UserMCPServer

pytestmark = pytest.mark.unit


class TestUserPluginModel:
    def test_table_name_and_columns(self) -> None:
        mapper = inspect(UserPlugin)
        columns = {c.key for c in mapper.columns}

        assert UserPlugin.__tablename__ == "user_plugins"
        assert {
            "id",
            "user_id",
            "name",
            "version",
            "description",
            "manifest",
            "spec_version",
        } <= columns

    def test_user_fk_cascades_on_user_deletion(self) -> None:
        user_id_col = inspect(UserPlugin).columns["user_id"]
        [fk] = user_id_col.foreign_keys

        assert fk.ondelete == "CASCADE"
        assert user_id_col.nullable is False

    def test_name_is_unique_per_user_not_globally(self) -> None:
        table = UserPlugin.__table__
        unique_constraints = [
            tuple(c.name for c in constraint.columns)
            for constraint in table.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
        ]

        assert ("user_id", "name") in unique_constraints

    def test_instantiates_with_manifest_payload(self) -> None:
        plugin = UserPlugin(
            user_id=uuid4(),
            name="acme.tools",
            version="1.2.0",
            description="Test plugin",
            manifest={"name": "acme.tools"},
            spec_version="1.0.0",
        )

        assert plugin.name == "acme.tools"
        assert plugin.manifest == {"name": "acme.tools"}


class TestProvenanceLinks:
    @pytest.mark.parametrize("model", [Skill, UserMCPServer])
    def test_plugin_id_is_nullable_set_null_fk(self, model: type) -> None:
        plugin_id_col = inspect(model).columns["plugin_id"]
        [fk] = plugin_id_col.foreign_keys

        assert plugin_id_col.nullable is True
        assert fk.ondelete == "SET NULL"
        assert fk.column.table.name == "user_plugins"
