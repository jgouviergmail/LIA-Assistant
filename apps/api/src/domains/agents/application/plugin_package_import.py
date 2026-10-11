"""One original native plugin write boundary for remote and browser-selected packages."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.plugin_import_guard import PluginImportGuard
from src.domains.agents.application.plugin_package_models import (
    PluginPackageCheck,
    PluginPackageWrite,
)
from src.domains.plugins.import_hooks import PluginImportHooks
from src.domains.plugins.import_service import PluginImportService
from src.domains.plugins.models import UserPlugin
from src.domains.plugins.public_report import public_plugin_report
from src.domains.plugins.root_commit import (
    PluginImportCompletionUnknown,
    PluginImportPostCommitFailure,
)
from src.domains.skills.import_commit import SkillImportCompletionUnknown
from src.domains.users.preference_cas import PreferenceWriteReceipt


async def install_plugin_package(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    write: PluginPackageWrite,
    receipt: PreferenceWriteReceipt,
    check: PluginPackageCheck,
) -> None:
    if (
        len(write.package.model_dump_json().encode("utf-8")) > 64_000
        or len(write.state.model_dump_json().encode("utf-8")) > 64_000
    ):
        raise CommandRejected("INVALID_INPUT")
    guard = PluginImportGuard(actor_id, draft, write, receipt, check)

    def committed(row: UserPlugin) -> None:
        receipt.committed = True
        receipt.values = {
            write.value_field: {
                "plugin_id": str(row.id),
                "name": row.name,
                "version": row.version,
                "complete": True,
            },
            "file_cleanup_pending": True,
            "cache_refresh_pending": True,
        }

    try:
        report = await PluginImportService(db).import_upload(
            write.content,
            owner_id=actor_id,
            hooks=PluginImportHooks(
                before_write=guard.before_write,
                before_skill_swap=guard.before_skill_swap,
                before_drop=guard.before_drop,
                before_server_write=guard.before_server_write,
                after_server_write=guard.server_written,
                after_plugin_write=guard.plugin_written,
                after_drop_stage=guard.after_drop_stage,
                after_root_stage=guard.after_root_stage,
                before_commit=guard.before_commit,
                after_skill_commit=guard.skill_committed,
                after_root_commit=committed,
            ),
        )
    except PluginImportPostCommitFailure as error:
        receipt.committed = True
        receipt.values = {
            write.value_field: {
                "plugin_id": str(guard.plugin_id),
                "name": write.package.name,
                "version": write.package.version,
                "complete": True,
            },
            "file_cleanup_pending": True,
            "cache_refresh_pending": True,
        }
        raise CommandRejected("POST_COMMIT_FAILURE") from error
    except (PluginImportCompletionUnknown, SkillImportCompletionUnknown) as error:
        if receipt.values is not None:
            receipt.values["completion_unknown"] = True
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.values = {
        write.value_field: public_plugin_report(report).model_dump(mode="json"),
        "file_cleanup_pending": report.file_cleanup_pending,
        "cache_refresh_pending": False,
    }
