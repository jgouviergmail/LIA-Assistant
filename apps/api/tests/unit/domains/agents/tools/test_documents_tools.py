"""Documents domain — RAG Spaces as an active routable capability (P1, ADR-141).

The passive last-message injection stays; this tool lets the planner/ReAct
iterate over the user's document spaces with derived queries and combine
them with other domains.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.registry.domain_taxonomy import DOMAIN_REGISTRY


@pytest.mark.unit
class TestDocumentDomainTaxonomy:
    def test_document_domain_registered_and_routable(self):
        config = DOMAIN_REGISTRY["document"]
        assert config.is_routable is True
        assert config.result_key == "documents"
        assert config.agent_names == ["document_agent"]

    # The chokepoint reads `settings` from whichever module hosts it (it moved
    # to analysis/domain_availability.py when the analyzer was shrunk under its
    # size ratchet). Patching the SETTINGS ATTRIBUTES rather than a module's
    # imported `settings` symbol keeps these tests bound to the behaviour
    # instead of to the current file layout — the earlier form silently stopped
    # constraining anything the day the function moved.
    def test_chokepoint_filters_domain_when_rag_disabled(self):
        from src.domains.agents.services.query_analyzer_service import (
            _build_available_domains,
        )

        with (
            patch("src.core.config.settings.telephony_enabled", False),
            patch("src.core.config.settings.rag_spaces_enabled", False),
            patch(
                "src.infrastructure.mcp.registration.get_admin_mcp_domains",
                return_value={},
            ),
        ):
            names = {d["name"] for d in _build_available_domains()}

        assert "document" not in names

    def test_chokepoint_keeps_domain_when_rag_enabled(self):
        from src.domains.agents.services.query_analyzer_service import (
            _build_available_domains,
        )

        with (
            patch("src.core.config.settings.telephony_enabled", False),
            patch("src.core.config.settings.rag_spaces_enabled", True),
            patch(
                "src.infrastructure.mcp.registration.get_admin_mcp_domains",
                return_value={},
            ),
        ):
            names = {d["name"] for d in _build_available_domains()}

        assert "document" in names


def _chunk(
    content="Le devis total est de 4 200 €", space="Devis", filename="devis.pdf", score=0.91
):
    return SimpleNamespace(
        content=content,
        space_name=space,
        original_filename=filename,
        score=score,
    )


def _runtime_ok():
    runtime = MagicMock()
    return runtime


@pytest.mark.unit
class TestSearchUserDocumentsTool:
    async def _call(self, *, rag_result, flag=True, query="montant du devis"):
        from contextlib import asynccontextmanager

        from src.domains.agents.tools import documents_tools

        @asynccontextmanager
        async def _db_ctx():
            yield MagicMock()

        config = SimpleNamespace(user_id=str(uuid4()))
        with (
            patch.object(
                documents_tools,
                "validate_runtime_config",
                return_value=config,
            ),
            patch.object(
                documents_tools,
                "settings",
                SimpleNamespace(rag_spaces_enabled=flag),
            ),
            patch("src.infrastructure.database.session.get_db_context", new=_db_ctx),
            patch(
                "src.domains.rag_spaces.retrieval.retrieve_rag_context",
                AsyncMock(return_value=rag_result),
            ),
        ):
            return await documents_tools.search_user_documents_tool.coroutine(
                query=query, runtime=_runtime_ok()
            )

    async def test_maps_chunks_to_documents(self):
        rag_result = SimpleNamespace(chunks=[_chunk()], spaces_searched=["Devis"])
        output = await self._call(rag_result=rag_result)

        assert output.success is True
        docs = output.structured_data["documents"]
        assert docs[0]["space"] == "Devis"
        assert docs[0]["filename"] == "devis.pdf"
        assert "4 200" in docs[0]["content"]
        assert output.structured_data["count"] == 1

    async def test_flag_off_returns_friendly_failure(self):
        output = await self._call(rag_result=None, flag=False)
        assert output.success is False
        assert output.error_code == "documents_not_configured"

    async def test_empty_result_is_success_with_zero(self):
        output = await self._call(rag_result=None)
        assert output.success is True
        assert output.structured_data["count"] == 0
