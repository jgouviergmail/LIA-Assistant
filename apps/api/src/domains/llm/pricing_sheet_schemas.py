"""API contracts for the pricing workbook import (ADR-228).

Issues travel as **codes and parameters**, never as sentences: the frontend
resolves them in the administrator's language, so the API never ships
pre-translated strings — and a code can be rendered as a link to the offending
cell, which a sentence cannot.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SheetIssue(BaseModel):
    """One problem, located as precisely as it can be."""

    model_config = ConfigDict(from_attributes=True)

    code: str = Field(description="Taxonomy code, resolved client-side")
    sheet: str | None = Field(default=None, description="Worksheet the problem is on")
    cell: str | None = Field(default=None, description="Excel coordinate, e.g. 'C42'")
    column: str | None = Field(default=None, description="Technical column key")
    params: dict[str, str] = Field(
        default_factory=dict, description="Values the translated message interpolates"
    )


class SheetFieldChange(BaseModel):
    """One field moving, rendered so the preview can show it verbatim."""

    field: str = Field(description="Technical column key")
    before: str | None = Field(default=None, description="Current value")
    after: str | None = Field(default=None, description="Value the file carries")


class SheetModelChange(BaseModel):
    """What the import would do to one model."""

    model_config = ConfigDict(protected_namespaces=())

    model_name: str = Field(description="Model the change applies to")
    action: str = Field(description="create | update | deactivate | reactivate | unchanged")
    fields: list[SheetFieldChange] = Field(default_factory=list)
    slots_before: int = Field(default=0, description="Time windows currently stored")
    slots_after: int = Field(default=0, description="Time windows the file declares")
    row_number: int | None = Field(default=None, description="Worksheet row, for a deep link")


class PricingSheetPlan(BaseModel):
    """The reviewed diff — what a dry run returns and an apply must match."""

    plan_fingerprint: str = Field(
        description=(
            "Hash of the plan. Applying re-derives the plan and refuses a "
            "different one, so the preview an administrator approved is the "
            "preview that gets written."
        )
    )
    counts: dict[str, int] = Field(description="How many rows per action")
    changes: list[SheetModelChange] = Field(default_factory=list)
    issues: list[SheetIssue] = Field(default_factory=list)
    is_applicable: bool = Field(description="False when any issue forbids writing")
    pricing_changes: list[str] = Field(
        default_factory=list, description="Models whose tariff would be superseded"
    )


class PricingSheetImportReport(BaseModel):
    """What an import did — the plan it applied, and the outcome."""

    applied: bool = Field(description="False for a dry run, or for a refused plan")
    plan: PricingSheetPlan = Field(description="The diff, reviewed or applied")
    created: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    deactivated: list[str] = Field(default_factory=list)
    reactivated: list[str] = Field(default_factory=list)
    unchanged: int = Field(default=0, description="Rows the file left as they were")
