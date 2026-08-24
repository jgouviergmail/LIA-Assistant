"""Export and import endpoints for the LLM pricing workbook (ADR-228).

Kept out of ``router.py`` on purpose: that module is already the LLM admin API
and the workbook has its own vocabulary. The two routes are thin — every rule
lives in the domain, and the route only carries language, limits and the
transaction boundary.

The import is deliberately two-phase. A dry run returns the plan and writes
nothing; applying re-derives the plan from the same file and refuses if it no
longer matches the one that was reviewed, so a preview an administrator
approved is the preview that gets written.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.exceptions import raise_invalid_input
from src.core.i18n_pricing_sheet import build_sheet_labels, build_sheet_notice
from src.core.session_dependencies import get_current_superuser_session
from src.domains.llm.pricing_change_plan import ChangePlan, build_change_plan
from src.domains.llm.pricing_import_service import ImportOutcome, PricingImportService
from src.domains.llm.pricing_sheet import MODELS_SHEET, SLOTS_SHEET, build_pricing_workbook_spec
from src.domains.llm.pricing_sheet_rows import ExportPayload, build_export_rows
from src.domains.llm.pricing_sheet_schemas import (
    PricingSheetImportReport,
    PricingSheetPlan,
    SheetFieldChange,
    SheetIssue,
    SheetModelChange,
)
from src.domains.users.models import AdminAuditLog, User
from src.infrastructure.tabular_io.reader import parse_workbook
from src.infrastructure.tabular_io.report import ParsedRow, ParsedWorkbook
from src.infrastructure.tabular_io.spec import WorkbookSpec
from src.infrastructure.tabular_io.writer import build_workbook

logger = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/admin/llm/pricing/sheet",
    tags=["admin", "llm"],
    dependencies=[Depends(get_current_superuser_session)],
)

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_EXPORT_FILENAME = "lia-llm-pricing.xlsx"

#: Read in bounded chunks so an oversized upload is refused before it is held
#: in memory in full.
_UPLOAD_CHUNK_BYTES = 64 * 1024


@router.get(
    "/export.xlsx",
    summary="Download the LLM catalogue as a workbook",
    description=(
        "Export every model with its characteristics, its current tariff and "
        "its UTC time windows. Read-only diagnostic columns state what the "
        "runtime would really do — a model with no active tariff is billed "
        "zero in silence, and the file says so."
    ),
)
async def export_pricing_sheet(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> StreamingResponse:
    """Build the workbook in the administrator's language."""
    labels = build_sheet_labels(current_user.language)
    payload = await build_export_rows(db, labels=labels)
    spec = build_pricing_workbook_spec()

    content = build_workbook(
        spec,
        {MODELS_SHEET.name: payload.models, SLOTS_SHEET.name: payload.slots},
        notice=build_sheet_notice(current_user.language),
        labels=labels,
        metadata={"exported_by": current_user.email, "model_count": str(len(payload.models))},
    )

    logger.info(
        "llm_pricing_sheet_exported",
        models=len(payload.models),
        slots=len(payload.slots),
        bytes=len(content),
        admin_user_id=str(current_user.id),
    )
    return StreamingResponse(
        iter([content]),
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{_EXPORT_FILENAME}"'},
    )


@router.post(
    "/import",
    response_model=PricingSheetImportReport,
    status_code=status.HTTP_200_OK,
    summary="Preview or apply an edited workbook",
    description=(
        "With `dry_run=true` (the default) nothing is written: the full plan "
        "comes back, field by field. Applying re-derives the plan and refuses "
        "a different one, so what was reviewed is what gets written. An import "
        "is all-or-nothing: a single unresolved problem writes nothing."
    ),
)
async def import_pricing_sheet(
    file: Annotated[UploadFile, File(description="The edited .xlsx workbook")],
    dry_run: Annotated[bool, Query(description="Preview only; write nothing")] = True,
    plan_fingerprint: Annotated[
        str | None,
        Query(description="Fingerprint of the reviewed plan; required to apply"),
    ] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_superuser_session),
) -> PricingSheetImportReport:
    """Diff an uploaded workbook against the catalogue, and optionally apply it."""
    content = await _read_capped(file)

    labels = build_sheet_labels(current_user.language)
    payload = await build_export_rows(db, labels=labels)
    spec = build_pricing_workbook_spec()
    parsed = _parse(spec, content)

    stored = _stored_slots(payload)
    plan = build_change_plan(
        db_rows=payload.models,
        sheet_rows=parsed.rows(MODELS_SHEET.name),
        sheet_slots=parsed.rows(SLOTS_SHEET.name),
        db_slots=stored,
    )
    plan_view = _to_plan_view(plan, parsed)

    if dry_run:
        logger.info(
            "llm_pricing_sheet_previewed",
            # The view's verdict, not the diff's: it folds the parser's issues
            # in, so the log cannot claim "applicable" for a file the response
            # just refused.
            applicable=plan_view.is_applicable,
            issues=len(plan_view.issues),
            admin_user_id=str(current_user.id),
        )
        return PricingSheetImportReport(applied=False, plan=plan_view)

    _guard_apply(plan_view, plan_fingerprint)

    outcome = await PricingImportService(db).apply(
        plan,
        sheet_rows=parsed.rows(MODELS_SHEET.name),
        sheet_slots=parsed.rows(SLOTS_SHEET.name),
    )
    db.add(
        AdminAuditLog(
            admin_user_id=str(current_user.id),
            action="llm_pricing_sheet_imported",
            resource_type="llm_models",
            details={
                "created": list(outcome.created),
                "updated": list(outcome.updated),
                "deactivated": list(outcome.deactivated),
                "reactivated": list(outcome.reactivated),
                "unchanged": outcome.unchanged,
                "plan_fingerprint": plan_view.plan_fingerprint,
            },
        )
    )
    await db.commit()

    # Caches are refreshed only once the write is committed: a cache rebuilt
    # from an uncommitted transaction would publish prices that never landed.
    from src.domains.llm.router import _invalidate_caches

    await _invalidate_caches(db)

    logger.info(
        "llm_pricing_sheet_imported",
        created=len(outcome.created),
        updated=len(outcome.updated),
        deactivated=len(outcome.deactivated),
        reactivated=len(outcome.reactivated),
        unchanged=outcome.unchanged,
        admin_user_id=str(current_user.id),
    )
    return _to_report(plan_view, outcome)


async def _read_capped(file: UploadFile) -> bytes:
    """Read the upload, refusing it as soon as it passes the size budget.

    Chunked on purpose: reading first and measuring afterwards would hold an
    oversized file in memory in full before deciding to reject it.
    """
    limit = settings.llm_sheet_max_upload_kb * 1024
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
        total += len(chunk)
        if total > limit:
            raise_invalid_input(
                f"workbook exceeds the {settings.llm_sheet_max_upload_kb}KB limit",
                limit_kb=settings.llm_sheet_max_upload_kb,
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _parse(spec: WorkbookSpec, content: bytes) -> ParsedWorkbook:
    """Parse the upload under the configured guards."""
    return parse_workbook(
        spec,
        content,
        max_rows=settings.llm_sheet_max_rows,
        max_files=settings.llm_sheet_zip_max_files,
        max_decompressed_bytes=settings.llm_sheet_zip_max_decompressed_kb * 1024,
    )


def _stored_slots(payload: ExportPayload) -> list[ParsedRow]:
    """Present the stored windows in the shape the diff compares against.

    Built directly rather than by rendering a whole workbook and reading it
    back: the row builder already yields the same Decimals the parser produces,
    and the comparison normalises both sides anyway — so the round trip only
    cost a full 124-model render on every single import.
    """
    return [
        ParsedRow(row_number=index, key=str(window["model_name"]), values=dict(window))
        for index, window in enumerate(payload.slots, start=1)
    ]


def _guard_apply(plan_view: PricingSheetPlan, supplied_fingerprint: str | None) -> None:
    """Refuse to write anything the administrator has not actually reviewed.

    The view's verdict is the one that counts: it folds the parser's issues in
    with the diff's, and a file that could not be read must not be applied
    merely because the diff it produced happened to look clean.
    """
    if not plan_view.is_applicable:
        raise_invalid_input(
            "the workbook carries unresolved problems and cannot be applied",
            issues=len(plan_view.issues),
        )
    if not supplied_fingerprint:
        raise_invalid_input(
            "applying requires the fingerprint of the reviewed plan",
            expected=plan_view.plan_fingerprint,
        )
    if supplied_fingerprint != plan_view.plan_fingerprint:
        raise_invalid_input(
            "the catalogue changed since this plan was reviewed; preview it again",
            expected=plan_view.plan_fingerprint,
            supplied=supplied_fingerprint,
        )


def _to_plan_view(plan: ChangePlan, parsed: ParsedWorkbook) -> PricingSheetPlan:
    """Render the domain plan as the API contract, issues included."""
    issues = [
        SheetIssue(
            code=issue.code.value,
            sheet=issue.sheet,
            cell=issue.cell,
            column=issue.column,
            params=dict(issue.params),
        )
        for issue in (*parsed.issues, *plan.issues)
    ]
    return PricingSheetPlan(
        plan_fingerprint=plan.fingerprint(),
        counts={action.value: count for action, count in plan.counts.items()},
        changes=[
            SheetModelChange(
                model_name=change.model_name,
                action=change.action.value,
                fields=[
                    SheetFieldChange(field=f.field, before=f.before, after=f.after)
                    for f in change.fields
                ],
                slots_before=change.slots_before,
                slots_after=change.slots_after,
                row_number=change.row_number,
            )
            for change in plan.changes
        ],
        issues=issues,
        is_applicable=plan.is_applicable and not parsed.issues,
        pricing_changes=list(plan.pricing_changes),
    )


def _to_report(plan_view: PricingSheetPlan, outcome: ImportOutcome) -> PricingSheetImportReport:
    return PricingSheetImportReport(
        applied=True,
        plan=plan_view,
        created=list(outcome.created),
        updated=list(outcome.updated),
        deactivated=list(outcome.deactivated),
        reactivated=list(outcome.reactivated),
        unchanged=outcome.unchanged,
    )
