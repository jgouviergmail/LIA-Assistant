"""
EmailCard Component - Modern Email Preview (v3.1).

Renders email as a premium Gmail-style card with:
- Clear unread indicator (sidebar + badge + bold text + background)
- Clean sender avatar with initials
- Subject and date in header
- Sender/recipients display
- Thread count and attachment badges
- Collapsible body with proper formatting
- Responsive design (mobile/tablet/desktop)

Architecture v3.1 - Gmail-inspired modern design.
"""

from __future__ import annotations

from typing import Any

from src.core.config import settings
from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    compact_html,
    escape_html,
    format_date,
    format_email_body,
    markdown_links_to_html,
    render_attachments,
    render_chip,
    render_chip_row,
    render_collapsible,
    render_desc_block,
    render_part_list,
    render_section_header,
    truncate,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, icon


class EmailCard(BaseComponent):
    """
    Modern email preview card (v3.1 - Gmail-inspired).

    Design principles:
    - Immediate scanability: unread state obvious at a glance
    - Visual hierarchy: subject > sender > recipients > body
    - Clean typography: proper spacing and line heights
    - Domain-specific accent: Gmail red theme
    """

    # Default suggested actions for emails
    DEFAULT_ACTIONS = [
        {"icon": Icons.REPLY, "label": "Répondre", "action": "reply"},
        {"icon": Icons.FORWARD, "label": "Transférer", "action": "forward"},
        {"icon": Icons.ARCHIVE, "label": "Archiver", "action": "archive"},
    ]

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
        """
        Render email as modern card with optional wrapper.

        Args:
            data: Email data dict
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional LLM comment to display above card
            suggested_actions: Optional action buttons (defaults to reply/forward/archive)
            with_wrapper: If True, wrap with response zones
            is_first_item: If True, add top separator (for list rendering)
            is_last_item: If True, add bottom separator (for list rendering)

        Returns:
            HTML string
        """
        # Extract data with safe defaults
        subject = data.get("subject") or V3Messages.get_no_subject(ctx.language)
        sender_name = self._get_sender(data)
        sender_email = self._get_sender_email(data)
        date_raw = data.get("date") or data.get("internalDate", "")
        snippet = data.get("snippet", "")
        is_unread = self._is_unread(data)
        has_attachments = bool(data.get("attachments") or data.get("hasAttachment"))
        is_important = data.get("isImportant", False) or "IMPORTANT" in data.get("labelIds", [])
        thread_count = data.get("threadCount", 1)
        attachments = data.get("attachments", [])

        # Build email web URL (provider-aware: Gmail has per-message URLs, Apple does not)
        url = self._build_email_web_url(data)

        # Format date with full date + time (using format_date with relative for recent, short for older)
        date_formatted = format_date(
            date_raw,
            language=ctx.language,
            timezone=ctx.timezone,
            format_type="relative",
            include_time=True,
        )

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            subject=subject,
            url=url,
            sender_name=sender_name,
            sender_email=sender_email,
            date_formatted=date_formatted,
            snippet=snippet,
            is_unread=is_unread,
            has_attachments=has_attachments,
            is_important=is_important,
            thread_count=thread_count,
            attachments=attachments,
            ctx=ctx,
            data=data,
        )

        # Wrap with response zones if requested
        if with_wrapper:
            actions = (
                suggested_actions
                if suggested_actions is not None
                else self._get_actions(ctx.language)
            )
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=actions,
                domain="email",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )

        return card_html

    def _render_card(
        self,
        subject: str,
        url: str,
        sender_name: str,
        sender_email: str,
        date_formatted: str,
        snippet: str,
        is_unread: bool,
        has_attachments: bool,
        is_important: bool,
        thread_count: int,
        attachments: list[dict[str, Any]],
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified email card using Design System v4 components."""
        unread_class = "lia-email--unread" if is_unread else "lia-email--read"
        important_class = "lia-email--important" if is_important else ""
        nested_class = self._nested_class(ctx)

        # --- Card top: initials illus (square rounded) + sender info + date ---
        initials = self._get_initials(sender_name)
        # Build subtitle with sender email + date + status icons
        subtitle_parts = []
        if sender_email and sender_email.lower() != sender_name.lower():
            subtitle_parts.append(escape_html(sender_email))
        subtitle_parts.append(escape_html(date_formatted))
        status_icons_html = self._render_status_icons(is_unread, is_important)

        # Sender name as mailto link
        if sender_email:
            title_html = (
                f'<a class="lia-card-top__title" href="mailto:{escape_html(sender_email)}">'
                f"{escape_html(sender_name)}</a>"
            )
        else:
            title_html = f'<span class="lia-card-top__title">{escape_html(sender_name)}</span>'

        subtitle_html = " · ".join(subtitle_parts)
        if status_icons_html:
            subtitle_html += f" {status_icons_html}"

        # Choose illus color based on email status
        if is_unread and is_important:
            illus_color = "red"
        elif is_unread:
            illus_color = "green"
        elif is_important:
            illus_color = "amber"
        else:
            illus_color = "gray"

        # Build card-top manually to insert initials text in illus
        card_top_html = compact_html(f"""
            <div class="lia-card-top">
                <div class="lia-illus lia-illus--{illus_color}">
                    <span style="font-size:var(--lia-text-sm);font-weight:600;letter-spacing:-0.02em">{escape_html(initials)}</span>
                </div>
                <div class="lia-card-top__info">
                    {title_html}
                    <div class="lia-card-top__subtitle">{subtitle_html}</div>
                </div>
            </div>
        """)

        # --- Subject line ---
        bold_class = "font-weight:700" if is_unread else "font-weight:600"
        subject_html = (
            f'<a href="{escape_html(url)}" class="lia-email__subject" '
            f'target="_blank" rel="noopener" style="{bold_class}">'
            f"{escape_html(subject)}</a>"
        )

        # --- Chips row: thread + attachments ---
        chips = []
        if thread_count > 1:
            chips.append(render_chip(f"{thread_count}", "thread", Icons.FORUM))
        if has_attachments:
            att_count = len(attachments) or 1
            chips.append(render_chip(f"{att_count}", "attach", Icons.ATTACHMENT))
        chip_row_html = render_chip_row(" ".join(chips)) if chips else ""

        # --- Labels ---
        labels_html = self._render_user_labels(data.get("labelIds", []))

        # --- Snippet ---
        snippet_html = (
            f'<p class="lia-email__snippet">{escape_html(truncate(snippet, 200))}</p>'
            if snippet
            else ""
        )

        # --- Collapsible body (recipients + content + attachments) ---
        body_html = self._render_body_v4(data, url, ctx)
        collapsible_attachments = self._render_collapsible_details(attachments, ctx)

        return compact_html(f"""
            <div class="lia-card lia-email {unread_class} {important_class} {nested_class}">
                {card_top_html}
                {subject_html}
                {chip_row_html}
                {labels_html}
                {snippet_html}
                {body_html}
                {collapsible_attachments}
            </div>
        """)

    def _render_body_v4(
        self,
        data: dict[str, Any],
        url: str,
        ctx: RenderContext,
    ) -> str:
        """Render email body in collapsible with v4 components.

        Includes recipients (To/Cc) with name+email per line,
        then body content without blue left border.
        """
        content_parts: list[str] = []

        # To recipients section
        to_recipients = data.get("to", [])
        if to_recipients:
            to_label = V3Messages.get_to(ctx.language)
            content_parts.append(
                render_section_header(to_label, Icons.PERSON, "indigo", first=True)
            )
            # Build participant-like list from recipients
            part_data = self._recipients_to_part_data(to_recipients)
            content_parts.append(render_part_list(part_data))

        # Cc recipients section
        cc_recipients = data.get("cc", [])
        if cc_recipients:
            cc_label = V3Messages.get_cc(ctx.language)
            content_parts.append(render_section_header(cc_label, Icons.GROUP, "indigo"))
            part_data = self._recipients_to_part_data(cc_recipients)
            content_parts.append(render_part_list(part_data))

        # Body content
        body = data.get("body") or data.get("bodyPreview", "")
        if body:
            body_text, is_truncated = format_email_body(
                body,
                max_length=settings.emails_body_max_length,
                preserve_links=True,
            )

            # Read more link
            read_more_html = ""
            if is_truncated and url:
                provider = data.get("_provider", "")
                read_more_label = V3Messages.get_read_more(ctx.language, provider)
                read_more_html = (
                    f'<a href="{escape_html(url)}" class="lia-email__read-more" '
                    f'target="_blank" rel="noopener">{escape_html(read_more_label)} '
                    f"{icon(Icons.OPEN_IN_NEW)}</a>"
                )

            # Format body
            url_threshold = settings.emails_url_shorten_threshold
            link_label = V3Messages.get_link(ctx.language)
            body_lines = body_text.split("\n")
            body_formatted = "<br>".join(
                markdown_links_to_html(line, url_threshold, link_label) for line in body_lines
            )

            email_content_label = V3Messages.get_email_content(ctx.language)
            content_parts.append(
                render_section_header(email_content_label, Icons.DESCRIPTION, "indigo")
            )
            content_parts.append(render_desc_block(body_formatted, with_border=False))
            if read_more_html:
                content_parts.append(read_more_html)

        if content_parts:
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html="".join(content_parts),
                initially_open=False,
                language=ctx.language,
                with_separator=False,
            )

        elif data.get("snippet"):
            return (
                f'<p class="lia-email__snippet">{escape_html(truncate(data["snippet"], 200))}</p>'
            )

        return ""

    def _recipients_to_part_data(self, recipients: list[Any] | Any) -> list[dict[str, Any]]:
        """Convert email recipients to participant-list compatible format.

        Args:
            recipients: List of recipient dicts or strings

        Returns:
            List of dicts with displayName and email keys
        """
        if not isinstance(recipients, list):
            recipients = [recipients]

        result = []
        for r in recipients:
            if isinstance(r, dict):
                name = r.get("name") or r.get("email", "")
                email = r.get("email", "")
            else:
                r_str = str(r)
                if "<" in r_str:
                    name = r_str.split("<")[0].strip().strip('"')
                    email = r_str.split("<")[1].rstrip(">").strip()
                elif "@" in r_str:
                    name = r_str
                    email = r_str
                else:
                    name = r_str
                    email = ""
            result.append(
                {
                    "displayName": name,
                    "email": email,
                    "responseStatus": "accepted",  # No status for email recipients
                }
            )
        return result

    # =========================================================================
    # Rendering Helpers
    # =========================================================================

    def _render_status_icons(self, is_unread: bool, is_important: bool) -> str:
        """Render status icons for unread and important emails.

        Colors:
        - Unread only: green icon
        - Important only: orange icon
        - Unread + Important: both icons in red
        """
        if not is_unread and not is_important:
            return ""

        icons = []
        # Determine color class based on combined status
        if is_unread and is_important:
            color_class = "lia-email__status-icon--urgent"
        elif is_unread:
            color_class = "lia-email__status-icon--unread"
        else:  # important only
            color_class = "lia-email__status-icon--important"

        if is_important:
            icons.append(
                f'<span class="lia-email__status-icon {color_class}" title="Important">{icon(Icons.STAR, size="sm")}</span>'
            )
        if is_unread:
            icons.append(
                f'<span class="lia-email__status-icon {color_class}" title="Non lu">{icon(Icons.MARK_EMAIL_UNREAD, size="sm")}</span>'
            )

        return f'<div class="lia-email__status-icons">{" ".join(icons)}</div>'

    def _get_initials(self, name: str) -> str:
        """Extract initials from name (max 2 chars)."""
        if not name:
            return "?"
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[0].upper()

    def _render_user_labels(self, label_ids: list[str]) -> str:
        """Render user-defined Gmail labels (excluding system labels)."""
        if not label_ids:
            return ""

        # System labels to exclude
        system_labels = {
            "INBOX",
            "SENT",
            "DRAFT",
            "TRASH",
            "SPAM",
            "UNREAD",
            "STARRED",
            "IMPORTANT",
            "CATEGORY_PERSONAL",
            "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS",
            "CATEGORY_UPDATES",
            "CATEGORY_FORUMS",
        }

        user_labels = [
            label.replace("/", " › ")
            for label in label_ids
            if label not in system_labels and not label.startswith("CATEGORY_")
        ][:3]

        if not user_labels:
            return ""

        labels_parts = [
            f'<span class="lia-email__label">{escape_html(label)}</span>' for label in user_labels
        ]
        return f'<div class="lia-email__labels">{" ".join(labels_parts)}</div>'

    def _render_collapsible_details(
        self,
        attachments: list[dict[str, Any]],
        ctx: RenderContext,
    ) -> str:
        """Render collapsible section with attachments."""
        if not attachments:
            return ""

        content_html = render_attachments(attachments, max_attachments=5)
        trigger_text = V3Messages.get_see_attachments(ctx.language, len(attachments))

        return render_collapsible(
            trigger_text=trigger_text,
            content_html=content_html,
            initially_open=False,
            language=ctx.language,
        )

    def _format_recipients_list(self, recipients: list[Any] | Any) -> str:
        """Format list of recipients as comma-separated string."""
        if not recipients:
            return ""

        if not isinstance(recipients, list):
            recipients = [recipients]

        formatted = [self._format_recipient(r) for r in recipients[:5]]
        result = ", ".join(formatted)

        if len(recipients) > 5:
            result += f" (+{len(recipients) - 5})"

        return result

    def _get_actions(self, language: str) -> list[dict[str, str]]:
        """Get localized action buttons."""
        return [
            {"icon": Icons.REPLY, "label": V3Messages.get_reply(language), "action": "reply"},
            {"icon": Icons.FORWARD, "label": V3Messages.get_forward(language), "action": "forward"},
            {"icon": Icons.ARCHIVE, "label": V3Messages.get_archive(language), "action": "archive"},
        ]

    # =========================================================================
    # Data Extraction Helpers
    # =========================================================================

    def _build_email_web_url(self, data: dict[str, Any]) -> str:
        """Build web URL for an email message (provider-aware).

        - Gmail: direct link to message in Gmail web UI
        - Microsoft Outlook: webLink from Microsoft Graph API
        - Apple: empty string (iCloud Mail has no per-message URL)
        """
        provider = data.get("_provider")
        message_id = data.get("id", "")
        if not message_id:
            return ""
        if provider == "apple":
            return ""
        if provider == "microsoft":
            return str(data.get("webLink", ""))
        # Default: Gmail
        return f"https://mail.google.com/mail/u/0/#all/{message_id}"

    def _format_recipient(self, recipient: Any) -> str:
        """Format a recipient (dict or string) for display."""
        if isinstance(recipient, dict):
            return recipient.get("name") or recipient.get("email", "")  # type: ignore[no-any-return]
        recipient_str = str(recipient)
        if "<" in recipient_str:
            name = recipient_str.split("<")[0].strip().strip('"')
            if name:
                return name
            return recipient_str.split("<")[1].rstrip(">").strip()
        return recipient_str

    def _extract_recipient_email(self, recipient: Any) -> str:
        """Extract email address from a recipient (dict or string)."""
        if isinstance(recipient, dict):
            return recipient.get("email", "")  # type: ignore[no-any-return]
        recipient_str = str(recipient)
        if "<" in recipient_str:
            # Format: "Name <email@example.com>"
            return recipient_str.split("<")[1].rstrip(">").strip()
        # If it looks like an email (contains @), return it
        if "@" in recipient_str:
            return recipient_str.strip()
        return ""

    def _get_sender(self, data: dict) -> str:
        """Extract sender name. Falls back to email if name is empty."""
        sender = data.get("from") or data.get("sender", "")
        if isinstance(sender, dict):
            return sender.get("name") or sender.get("email", "")  # type: ignore[no-any-return]
        if isinstance(sender, str) and "<" in sender:
            name = sender.split("<")[0].strip().strip('"')
            if name:
                return name
            return sender.split("<")[1].rstrip(">").strip()
        return str(sender)

    def _get_sender_email(self, data: dict) -> str:
        """Extract sender email address."""
        sender = data.get("from") or data.get("sender", "")
        if isinstance(sender, dict):
            return sender.get("email", "")  # type: ignore[no-any-return]
        if isinstance(sender, str) and "<" in sender:
            return sender.split("<")[1].rstrip(">").strip()
        if isinstance(sender, str) and "@" in sender:
            return sender
        return ""

    def _is_unread(self, data: dict) -> bool:
        """Check if email is unread."""
        if data.get("unread"):
            return True
        labels = data.get("labelIds", [])
        return "UNREAD" in labels
