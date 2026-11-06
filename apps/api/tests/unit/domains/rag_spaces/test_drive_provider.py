"""A linked folder belongs to the drive it was linked on (ADR-369, lot 11).

An id means nothing on another drive, and one account connects one drive at a time: a folder of the
other is kept with its documents, and its synchronisation waits for that drive to come back.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.google_drive_client import GoogleDriveClient
from src.domains.connectors.clients.microsoft_onedrive_client import MicrosoftOneDriveClient
from src.domains.connectors.models import ConnectorType
from src.domains.rag_spaces import drive_sync
from src.domains.rag_spaces.drive_provider import (
    DRIVE_SOURCE_PAUSED_CODE,
    active_drive_provider,
    drive_client_of,
    is_paused,
)
from src.domains.rag_spaces.drive_sync import RAGDriveSyncService
from src.domains.rag_spaces.models import RAGDriveSource
from src.domains.rag_spaces.router import sync_drive_folder
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.rag_spaces.source_link_observation import linked_drive_roots

pytestmark = pytest.mark.unit

GOOGLE = ConnectorType.GOOGLE_DRIVE.value
ONEDRIVE = ConnectorType.MICROSOFT_ONEDRIVE.value


def _source(provider: str = GOOGLE, folder_id: str = "folder") -> Any:
    return SimpleNamespace(
        id=uuid4(), provider=provider, folder_id=folder_id, folder_ids=[folder_id]
    )


class TestTheRow:
    def test_a_folder_linked_before_this_is_google_s(self) -> None:
        column = RAGDriveSource.__table__.c.provider

        assert column.nullable is False
        assert column.server_default.arg == GOOGLE


class TestItsClient:
    @pytest.mark.parametrize(
        ("provider", "client_class"),
        [(GOOGLE, GoogleDriveClient), (ONEDRIVE, MicrosoftOneDriveClient)],
    )
    def test_the_client_is_the_one_of_its_drive(self, provider: str, client_class: type) -> None:
        client = drive_client_of(provider, uuid4(), MagicMock(), MagicMock())

        assert isinstance(client, client_class)


class TestTheActiveDrive:
    @pytest.mark.parametrize(
        ("connected", "expected"),
        [
            (ConnectorType.GOOGLE_DRIVE, GOOGLE),
            (ConnectorType.MICROSOFT_ONEDRIVE, ONEDRIVE),
            (None, None),
        ],
    )
    async def test_it_is_the_one_the_account_connected(
        self, connected: ConnectorType | None, expected: str | None
    ) -> None:
        with patch(
            "src.domains.rag_spaces.drive_provider.resolve_active_connector",
            AsyncMock(return_value=connected),
        ) as resolve:
            user_id = uuid4()
            service = MagicMock()

            assert await active_drive_provider(user_id, service) == expected

        resolve.assert_awaited_once_with(user_id, "files", service)


class TestAPausedFolder:
    def test_a_folder_of_the_connected_drive_answers(self) -> None:
        assert is_paused(_source(ONEDRIVE), ONEDRIVE) is False

    def test_a_folder_of_the_other_drive_waits(self) -> None:
        assert is_paused(_source(GOOGLE), ONEDRIVE) is True

    def test_with_no_drive_connected_every_folder_waits(self) -> None:
        assert is_paused(_source(GOOGLE), None) is True

    async def test_its_synchronisation_is_refused_by_a_code_the_screen_reads(self) -> None:
        source = _source(GOOGLE)
        service = RAGDriveSyncService(MagicMock())
        service._verify_space_ownership = AsyncMock()  # type: ignore[method-assign]
        service._get_source_or_404 = AsyncMock(return_value=source)  # type: ignore[method-assign]

        with (
            patch.object(drive_sync, "active_drive_provider", AsyncMock(return_value=ONEDRIVE)),
            pytest.raises(BaseAPIException) as refused,
        ):
            await service.require_live_source(uuid4(), source.id, uuid4())

        assert refused.value.status_code == 409
        assert refused.value.detail == {"code": DRIVE_SOURCE_PAUSED_CODE}

    async def test_a_live_folder_passes(self) -> None:
        source = _source(ONEDRIVE)
        service = RAGDriveSyncService(MagicMock())
        service._verify_space_ownership = AsyncMock()  # type: ignore[method-assign]
        service._get_source_or_404 = AsyncMock(return_value=source)  # type: ignore[method-assign]

        with patch.object(drive_sync, "active_drive_provider", AsyncMock(return_value=ONEDRIVE)):
            assert await service.require_live_source(uuid4(), source.id, uuid4()) is source


class TestTheSpaceSays:
    async def test_which_drive_is_connected_for_the_screen_to_judge_each_folder(self) -> None:
        service = RAGSpaceService(MagicMock())
        service.get_space = AsyncMock(return_value=MagicMock(dict=lambda: {"id": "s"}))  # type: ignore[method-assign]
        service.doc_repo = MagicMock(
            get_space_stats=AsyncMock(return_value={}), get_all_for_space=AsyncMock(return_value=[])
        )
        service.source_repo = MagicMock(get_all_for_space=AsyncMock(return_value=[]))
        service.mail_source_repo = MagicMock(get_all_for_space=AsyncMock(return_value=[]))

        with patch(
            "src.domains.rag_spaces.service.active_drive_provider",
            AsyncMock(return_value=ONEDRIVE),
        ):
            detail = await service.get_space_detail(uuid4(), uuid4())

        assert detail["active_drive"] == ONEDRIVE


class TestWhatAPausedFolderIsRefused:
    async def test_counting_what_a_sync_would_do(self) -> None:
        service = RAGDriveSyncService(MagicMock())
        service.require_live_source = AsyncMock(  # type: ignore[method-assign]
            side_effect=BaseAPIException(status_code=409, detail={"code": "x"}, log_event="x")
        )
        service._get_drive_client = AsyncMock()  # type: ignore[method-assign]

        with pytest.raises(BaseAPIException):
            await service.preflight(uuid4(), uuid4(), uuid4())

        service._get_drive_client.assert_not_awaited()

    async def test_a_sync_asked_on_the_screen(self) -> None:
        service = MagicMock(
            require_live_source=AsyncMock(
                side_effect=BaseAPIException(status_code=409, detail={"code": "x"}, log_event="x")
            ),
            try_acquire_sync_lock=AsyncMock(),
        )

        with (
            patch("src.domains.rag_spaces.router.RAGDriveSyncService", return_value=service),
            pytest.raises(BaseAPIException),
        ):
            await sync_drive_folder(uuid4(), uuid4(), MagicMock(id=uuid4()), MagicMock())

        service.try_acquire_sync_lock.assert_not_awaited()


class TestLinkedTrees:
    def test_a_tree_of_another_drive_shares_nothing_with_this_one(self) -> None:
        """Its ids mean nothing here: asking this drive about them would answer 404."""
        roots = linked_drive_roots([_source(GOOGLE, "g"), _source(ONEDRIVE, "o")], ONEDRIVE)

        assert [root.folder_id for root in roots] == ["o"]


class TestLinkingAFolder:
    @staticmethod
    def _service() -> RAGDriveSyncService:
        service = RAGDriveSyncService(MagicMock(commit=AsyncMock()))
        service._folder_link_constraints = AsyncMock()  # type: ignore[method-assign]
        service.source_repo = MagicMock(get_all_for_space=AsyncMock(return_value=[]))
        return service

    async def test_the_observation_names_the_drive_that_answered(self) -> None:
        service = self._service()
        client = MagicMock(
            connector_type=ConnectorType.MICROSOFT_ONEDRIVE,
            close=AsyncMock(),
            get_file_metadata=AsyncMock(
                return_value={
                    "id": "f1",
                    "name": "Notes",
                    "mimeType": "application/vnd.google-apps.folder",
                }
            ),
        )
        service._get_drive_client = AsyncMock(return_value=client)  # type: ignore[method-assign]

        observation = await service.prepare_folder_link(uuid4(), uuid4(), "f1")

        assert observation.drive_provider == ONEDRIVE

    async def test_the_source_keeps_it(self) -> None:
        service = self._service()
        service.space_repo = MagicMock(get_by_id_for_owner_update=AsyncMock(return_value=object()))
        service.source_repo.create = AsyncMock(return_value=MagicMock(id=uuid4()))
        service.db.flush = AsyncMock()
        space_id, user_id = uuid4(), uuid4()
        observation = drive_sync.SourceLinkObservation(
            "drive", space_id, user_id, "f1", "Notes", (), ONEDRIVE
        )

        await service.link_folder(
            space_id, user_id, "f1", "Notes", observation=observation, commit=False
        )

        assert service.source_repo.create.await_args.args[0]["provider"] == ONEDRIVE


class TestTheClientOfTheConnectedDrive:
    @pytest.mark.parametrize(
        ("connected", "client_class"),
        [
            (ConnectorType.GOOGLE_DRIVE, GoogleDriveClient),
            (ConnectorType.MICROSOFT_ONEDRIVE, MicrosoftOneDriveClient),
        ],
    )
    async def test_it_opens_whichever_is_connected(
        self, connected: ConnectorType, client_class: type
    ) -> None:
        connectors = MagicMock(get_connector_credentials=AsyncMock(return_value=MagicMock()))

        with (
            patch.object(drive_sync, "ConnectorService", return_value=connectors),
            patch.object(
                drive_sync, "active_drive_provider", AsyncMock(return_value=connected.value)
            ),
            patch.object(drive_sync, "DetachedConnectorService"),
        ):
            client = await RAGDriveSyncService(MagicMock())._get_drive_client(uuid4())

        assert isinstance(client, client_class)
        assert connectors.get_connector_credentials.await_args.args[1] is connected

    async def test_none_connected_is_said(self) -> None:
        with (
            patch.object(drive_sync, "ConnectorService"),
            patch.object(drive_sync, "active_drive_provider", AsyncMock(return_value=None)),
            pytest.raises(BaseAPIException) as refused,
        ):
            await RAGDriveSyncService(MagicMock())._get_drive_client(uuid4())

        assert refused.value.status_code == 400
