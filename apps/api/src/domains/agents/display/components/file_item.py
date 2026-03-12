"""
FileItem Component - Modern Drive File Display.

Renders files with type icon, name, and metadata.
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_FILES
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    format_full_date,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon


class FileItem(BaseComponent):
    """
    Modern file item component.

    Design:
    - File type icon (doc, sheet, slides, pdf, etc.)
    - Name as primary link
    - Modified date
    - Size and owner (desktop)
    - Shared badge if applicable
    """

    # MIME type to (icon_name, css_class, type_key) mapping
    # icon_name is a Material Symbols icon name
    # type_key is used with V3Messages.get_file_type() for i18n
    FILE_ICONS = {
        "application/vnd.google-apps.document": (Icons.FILE, "doc", "document"),
        "application/vnd.google-apps.spreadsheet": (Icons.SPREADSHEET, "sheet", "spreadsheet"),
        "application/vnd.google-apps.presentation": (Icons.PRESENTATION, "slides", "presentation"),
        "application/vnd.google-apps.folder": (Icons.FOLDER, "folder", "folder"),
        "application/vnd.google-apps.form": (Icons.NOTE, "form", "form"),
        "application/pdf": (Icons.PDF, "pdf", "pdf"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (
            Icons.FILE,
            "docx",
            "word",
        ),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": (
            Icons.SPREADSHEET,
            "xlsx",
            "excel",
        ),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
            Icons.PRESENTATION,
            "pptx",
            "powerpoint",
        ),
        "image/": (Icons.IMAGE, "image", "image"),
        "video/": (Icons.VIDEO, "video", "video"),
        "audio/": (Icons.AUDIO, "audio", "audio"),
        "text/": (Icons.NOTE, "text", "text"),
        "application/zip": (Icons.PACKAGE, "archive", "archive"),
    }

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render file as modern item with action buttons."""
        # Extract data
        title = data.get("title") or data.get("name") or V3Messages.get_no_name(ctx.language)
        url = data.get("url") or data.get("webViewLink", "")
        mime_type = data.get("mimeType", "")
        modified = data.get("modifiedTime") or data.get("modifiedDate", "")
        size = data.get("size", "")
        owner = self._get_owner(data)
        is_shared = data.get("shared", False)
        thumbnail = data.get("thumbnailLink", "")

        icon_name, file_class, type_key = self._get_file_visual(mime_type)
        type_label = V3Messages.get_file_type(ctx.language, type_key)
        # Use full date with time instead of relative date
        modified_str = format_full_date(modified, ctx.language, ctx.timezone, include_time=True)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(url, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            title,
            url,
            icon_name,
            file_class,
            type_label,
            modified_str,
            size,
            owner,
            is_shared,
            thumbnail,
            ctx,
            data,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_FILES,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self,
        url: str,
        ctx: RenderContext,
    ) -> list[dict[str, str]]:
        """Build default action buttons for file."""
        actions = []

        # View details (open file)
        if url:
            actions.append(
                {
                    "icon": Icons.FILE,
                    "label": V3Messages.get_view_details(ctx.language),
                    "url": url,
                }
            )

        # Delete action
        actions.append(
            {
                "icon": Icons.DELETE,
                "label": V3Messages.get_delete(ctx.language),
                "url": "",  # Will be handled by frontend
                "action": "delete",
            }
        )

        return actions

    def _render_card(
        self,
        title: str,
        url: str,
        icon_name: str,
        file_class: str,
        type_label: str,
        modified: str,
        size: str,
        owner: str,
        is_shared: bool,
        thumbnail: str,
        ctx: RenderContext,
        data: dict[str, Any] | None = None,
    ) -> str:
        """Unified file card - CSS handles responsive adaptation."""
        nested_class = self._nested_class(ctx)

        # Thumbnail for images
        thumb_html = ""
        if thumbnail and "image" in file_class:
            thumb_html = f'<img src="{escape_html(thumbnail)}" alt="" class="lia-file__thumb" loading="lazy">'

        # Size formatting
        size_str = self._format_size_i18n(size, ctx.language) if size else ""

        # Starred (from SEARCH_FIELDS)
        is_starred = data.get("starred", False) if data else False

        # i18n labels
        favorite_label = V3Messages.get_favorite(ctx.language)
        shared_label = V3Messages.get_shared(ctx.language)
        created_label = V3Messages.get_created(ctx.language)
        modified_label = V3Messages.get_modified(ctx.language)

        # 1. Badges: type first, then starred, then shared
        badges = []
        badges.append(f'<span class="lia-badge lia-badge--subtle">{escape_html(type_label)}</span>')
        if is_starred:
            badges.append(
                f'<span class="lia-badge lia-badge--warning">{icon(Icons.STAR)} {escape_html(favorite_label)}</span>'
            )
        if is_shared:
            badges.append(
                f'<span class="lia-badge lia-badge--accent">{escape_html(shared_label)}</span>'
            )
        badges_html = " ".join(badges)

        # 3. Size + owner line
        size_owner_parts = []
        if size_str:
            size_owner_parts.append(escape_html(size_str))
        if owner:
            size_owner_parts.append(escape_html(owner))
        size_owner_html = " · ".join(size_owner_parts) if size_owner_parts else ""

        # 5. Footer with created date + icon
        footer_html = ""
        if data:
            created = data.get("createdTime", "")
            if created:
                created_str = format_full_date(
                    created, ctx.language, ctx.timezone, include_time=True
                )
                footer_html = f"""<div class="lia-file__footer">
      <span class="lia-file__created">{icon(Icons.CALENDAR, size="sm")} {escape_html(created_label)} : {escape_html(created_str)}</span>
    </div>"""

        # =====================================================================
        # DETAIL FIELDS: Only rendered if present (details mode has them)
        # =====================================================================
        detail_html = ""
        if data:
            detail_sections = []

            # Description
            description = data.get("description", "")
            if description:
                desc_preview = description[:150] + "..." if len(description) > 150 else description
                detail_sections.append(
                    f'<div class="lia-file__detail-item">'
                    f"{icon(Icons.NOTE)}"
                    f"<span>{escape_html(desc_preview)}</span>"
                    f"</div>"
                )

            # Content preview (for text files)
            content = data.get("content", "")
            if content and isinstance(content, str):
                content_preview = content[:200] + "..." if len(content) > 200 else content
                detail_sections.append(
                    f'<div class="lia-file__content-preview">'
                    f"{icon(Icons.FILE)}"
                    f"<span>{escape_html(content_preview)}</span>"
                    f"</div>"
                )

            # Sharing info
            permissions = data.get("permissions", [])
            if permissions and len(permissions) > 1:  # More than just owner
                shared_count = len(permissions) - 1
                shared_with_label = V3Messages.get_shared_with(ctx.language, shared_count)
                detail_sections.append(
                    f'<div class="lia-file__detail-item">'
                    f"{icon(Icons.GROUP)}"
                    f"<span>{escape_html(shared_with_label)}</span>"
                    f"</div>"
                )

            if detail_sections:
                detail_html = (
                    f'<div class="lia-file__extended">\n{"".join(detail_sections)}\n</div>'
                )

        # Only show thumbnail for images, no icon (badge type is sufficient)
        thumb_section = ""
        if thumb_html:
            thumb_section = f'<div class="lia-file__thumb-wrap">{thumb_html}</div>'

        # File path (full folder hierarchy) above the title
        path_html = ""
        if data:
            parent_path = data.get("parentPath", "")
            if parent_path:
                path_html = f'<div class="lia-file__path">{icon(Icons.FOLDER, size="sm")} {escape_html(parent_path)}</div>'

        return f"""<div class="lia-card lia-file lia-file--{file_class} {nested_class}">
  {thumb_section}
  <div class="lia-file__content">
    {path_html}
    <div class="lia-file__header">
      <a href="{escape_html(url)}" class="lia-file__name" target="_blank">{escape_html(title)}</a>
      <div class="lia-file__badges">{badges_html}</div>
    </div>
    <div class="lia-file__meta">
      {f'<div class="lia-file__size-owner">{size_owner_html}</div>' if size_owner_html else ''}
      <div class="lia-file__modified">{icon(Icons.EDIT, size="sm")} {escape_html(modified_label)} : {escape_html(modified)}</div>
    </div>
    {footer_html}
    {detail_html}
  </div>
</div>"""

    def _get_file_visual(self, mime_type: str) -> tuple[str, str, str]:
        """Get icon name, CSS class, and type_key for MIME type."""
        if not mime_type:
            return Icons.FILE, "generic", "file"

        # Exact match
        if mime_type in self.FILE_ICONS:
            return self.FILE_ICONS[mime_type]

        # Prefix match
        for prefix, (icon_name, css, type_key) in self.FILE_ICONS.items():
            if mime_type.startswith(prefix):
                return icon_name, css, type_key

        # Default
        return Icons.FILE, "generic", "file"

    def _get_owner(self, data: dict) -> str:
        """Extract owner name."""
        owners = data.get("owners", [])
        if owners and isinstance(owners, list):
            owner = owners[0]
            if isinstance(owner, dict):
                return owner.get("displayName") or owner.get("emailAddress", "")  # type: ignore[no-any-return]
        return ""

    def _format_size(self, size: str | int) -> str:
        """Format file size (French default for backward compat)."""
        try:
            bytes_size = int(size)
            if bytes_size < 1024:
                return f"{bytes_size} o"
            elif bytes_size < 1024 * 1024:
                return f"{bytes_size // 1024} Ko"
            elif bytes_size < 1024 * 1024 * 1024:
                return f"{bytes_size // (1024 * 1024)} Mo"
            else:
                return f"{bytes_size // (1024 * 1024 * 1024)} Go"
        except (ValueError, TypeError):
            return str(size) if size else ""

    def _format_size_i18n(self, size: str | int, language: str) -> str:
        """Format file size with i18n support."""
        try:
            bytes_size = int(size)
            if bytes_size < 1024:
                unit = V3Messages.get_size_unit(language, "b")
                return f"{bytes_size} {unit}"
            elif bytes_size < 1024 * 1024:
                unit = V3Messages.get_size_unit(language, "kb")
                return f"{bytes_size // 1024} {unit}"
            elif bytes_size < 1024 * 1024 * 1024:
                unit = V3Messages.get_size_unit(language, "mb")
                return f"{bytes_size // (1024 * 1024)} {unit}"
            else:
                unit = V3Messages.get_size_unit(language, "gb")
                return f"{bytes_size // (1024 * 1024 * 1024)} {unit}"
        except (ValueError, TypeError):
            return str(size) if size else ""
