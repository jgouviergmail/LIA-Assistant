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
    render_card_top,
    render_chip,
    render_chip_row,
    render_file_meta,
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

        # --- v4: card-top (icon + title) + chip row + file meta lines ---
        # Determine illus color from file type
        file_color_map = {
            "doc": "blue",
            "docx": "blue",
            "word": "blue",
            "sheet": "green",
            "xlsx": "green",
            "excel": "green",
            "slides": "orange",
            "pptx": "orange",
            "powerpoint": "orange",
            "pdf": "red",
            "image": "purple",
            "video": "purple",
            "audio": "purple",
            "folder": "amber",
            "form": "indigo",
            "text": "gray",
            "archive": "gray",
        }
        illus_color = file_color_map.get(file_class, "gray")
        title_html = f'<a class="lia-card-top__title" href="{escape_html(url)}" target="_blank">{escape_html(title)}</a>'
        card_top_html = render_card_top(icon_name, illus_color, title_html)

        # Chip row: type + shared? + starred? (separator both)
        chips = []
        chips.append(render_chip(type_label, illus_color.replace("gray", ""), icon_name))
        if is_starred:
            chips.append(render_chip(favorite_label, "stars", Icons.STAR))
        if is_shared:
            chips.append(render_chip(shared_label, "indigo", Icons.GROUP))
        chip_row_html = render_chip_row(" ".join(chips), separator_pos="bottom")

        # File meta lines
        meta_parts = []
        if data and data.get("parentPath"):
            meta_parts.append(render_file_meta(Icons.FOLDER, data["parentPath"]))
        if size_str:
            size_owner_text = size_str
            if owner:
                size_owner_text += f" · {owner}"
            meta_parts.append(render_file_meta("straighten", size_owner_text))
        meta_parts.append(render_file_meta(Icons.EDIT, f"{modified_label} : {modified}"))
        if data:
            created = data.get("createdTime", "")
            if created:
                created_str = format_full_date(
                    created, ctx.language, ctx.timezone, include_time=True
                )
                meta_parts.append(
                    render_file_meta(Icons.CALENDAR, f"{created_label} : {created_str}")
                )
        meta_html = "\n".join(meta_parts)

        return f"""<div class="lia-card lia-file lia-file--{file_class} {nested_class}">
{thumb_section}
{card_top_html}
{chip_row_html}
{meta_html}
{detail_html}
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
