"""Ticket categories API — the lanes of a board (ADR-276).

Mounted INSIDE the workboard router (``router.include_router``), so these
routes carry its prefix, its deployment flag and its operator switch without
restating any of them: a category is part of the board.

Like the ticket routes, this router owns the HTTP shape, the dependencies and
the transaction boundary, and decides nothing else. A category the caller does
not own answers the neutral 404 of one that does not exist.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.users.models import User
from src.domains.workboard.category_service import WorkboardCategoryService
from src.domains.workboard.schemas import (
    CategoryCreate,
    CategoryDeleteResult,
    CategoryList,
    CategoryRow,
    CategoryUpdate,
)

router = APIRouter()


@router.get(
    "/categories",
    response_model=CategoryList,
    summary="The categories on the caller's board, and the instance's caps",
    description=(
        "The caller's own categories in their order, then the categories of the "
        "tickets they hold for somebody else, each with its exact ticket count. "
        "The caps the instance enforces travel with the list."
    ),
)
async def list_categories(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CategoryList:
    """The categories on the caller's board.

    Args:
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The categories and the caps.
    """
    return await WorkboardCategoryService(db).listing(user)


@router.post(
    "/categories",
    response_model=CategoryRow,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
async def create_category(
    payload: CategoryCreate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CategoryRow:
    """Add a category — a lane — to the caller's board.

    Args:
        payload: The request.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The created category.
    """
    row = await WorkboardCategoryService(db).create(user, payload)
    await db.commit()
    return row


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryRow,
    summary="Rename a category or move it among the caller's own",
)
async def update_category(
    category_id: UUID,
    payload: CategoryUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CategoryRow:
    """Apply a partial update to one of the caller's categories.

    Args:
        category_id: The category.
        payload: What to change.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        The updated category.
    """
    row = await WorkboardCategoryService(db).update(user, category_id, payload)
    await db.commit()
    return row


@router.delete(
    "/categories/{category_id}",
    response_model=CategoryDeleteResult,
    summary="Delete a category; its tickets go back to the unfiled lane",
)
async def delete_category(
    category_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> CategoryDeleteResult:
    """Delete one of the caller's categories. No ticket is deleted.

    Args:
        category_id: The category.
        user: Authenticated session owner.
        db: Request-scoped session.

    Returns:
        How many tickets it released, so the caller can say what it did.
    """
    released = await WorkboardCategoryService(db).delete(user, category_id)
    await db.commit()
    return CategoryDeleteResult(released=released)
