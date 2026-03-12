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
    render_attachment_badge,
    render_attachments,
    render_collapsible,
    render_thread_badge,
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
        """Unified email card - CSS handles responsive adaptation."""
        unread_class = "lia-email--unread" if is_unread else "lia-email--read"
        important_class = "lia-email--important" if is_important else ""
        nested_class = self._nested_class(ctx)

        # Avatar
        avatar_html = self._render_avatar(sender_name)

        # Build badges
        badges = []
        if thread_count > 1:
            badges.append(render_thread_badge(thread_count))
        if has_attachments:
            att_count = len(attachments) or 1
            badges.append(render_attachment_badge(att_count))
        badges_html = " ".join(badges)

        # Unread badge
        unread_badge = self._render_unread_badge(is_unread, ctx.language)

        # Labels
        labels_html = self._render_user_labels(data.get("labelIds", []))

        # Body content with recipients inside collapsible
        body_html = self._render_body(data, snippet, url, ctx)

        # Collapsible details (attachments)
        collapsible_html = self._render_collapsible_details(attachments, ctx)

        # Sender name is always a mailto: link
        # Show email separately only if different from name
        if sender_email:
            sender_name_html = f'<a href="mailto:{escape_html(sender_email)}" class="lia-email__sender-name">{escape_html(sender_name)}</a>'
            if sender_email.lower() != sender_name.lower():
                sender_email_html = f'<a href="mailto:{escape_html(sender_email)}" class="lia-email__sender-email">{escape_html(sender_email)}</a>'
            else:
                sender_email_html = ""
        else:
            sender_name_html = (
                f'<span class="lia-email__sender-name">{escape_html(sender_name)}</span>'
            )
            sender_email_html = ""

        # Status icons (important/unread) - under date on desktop
        status_icons_html = self._render_status_icons(is_unread, is_important)

        return compact_html(
            f"""
            <div class="lia-card lia-email {unread_class} {important_class} {nested_class}">
                <div class="lia-email__avatar">{avatar_html}</div>
                <div class="lia-email__content">
                    <div class="lia-email__header-row">
                        <div class="lia-email__sender">
                            {sender_name_html}
                            {sender_email_html}
                        </div>
                        <div class="lia-email__header-right">
                            <span class="lia-email__date">{escape_html(date_formatted)}</span>
                            {status_icons_html}
                        </div>
                    </div>
                    <a href="{escape_html(url)}" class="lia-email__subject" target="_blank" rel="noopener">
                        {escape_html(subject)}
                    </a>
                    <div class="lia-email__meta">
                        {unread_badge}
                        {labels_html}
                        <div class="lia-email__badges">{badges_html}</div>
                    </div>
                    {body_html}
                    {collapsible_html}
                </div>
            </div>
        """
        )

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

    def _render_avatar(self, sender_name: str) -> str:
        """Render sender avatar with initials."""
        initials = self._get_initials(sender_name)
        return f'<div class="lia-email__avatar-circle">{escape_html(initials)}</div>'

    def _get_initials(self, name: str) -> str:
        """Extract initials from name (max 2 chars)."""
        if not name:
            return "?"
        parts = name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return name[0].upper()

    def _render_unread_badge(self, is_unread: bool, language: str) -> str:
        """Render unread/read status badge.

        Note: Badge disabled - unread state is already indicated by the
        colored left border (liseré), making the badge redundant.
        """
        # Unread state shown via border-left color, badge is redundant
        return ""

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

    def _render_recipients(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render To/Cc recipients (icons only, no labels - redundant)."""
        parts = []

        to_recipients = data.get("to", [])
        if to_recipients:
            to_list = self._format_recipients_list(to_recipients)
            parts.append(
                f'<div class="lia-email__recipient-row">'
                f"{icon(Icons.PERSON)}"
                f'<span class="lia-email__recipient-list">{escape_html(to_list)}</span>'
                f"</div>"
            )

        cc_recipients = data.get("cc", [])
        if cc_recipients:
            cc_list = self._format_recipients_list(cc_recipients)
            parts.append(
                f'<div class="lia-email__recipient-row">'
                f"{icon(Icons.GROUP)}"
                f'<span class="lia-email__recipient-list">{escape_html(cc_list)}</span>'
                f"</div>"
            )

        if not parts:
            return ""

        return f'<div class="lia-email__recipients">{" ".join(parts)}</div>'

    def _render_body(
        self,
        data: dict[str, Any],
        snippet: str,
        url: str,
        ctx: RenderContext,
    ) -> str:
        """Render email body in a collapsible 'Voir plus' section with responsive design.

        Recipients (To/Cc) are placed before the body content.
        """
        body = data.get("body") or data.get("bodyPreview", "")
        content_parts = []

        # Add recipients (To) section FIRST - with icon, aligned with title
        to_recipients = data.get("to", [])
        if to_recipients:
            to_label = V3Messages.get_to(ctx.language)
            to_list_html = self._render_recipients_vertical(to_recipients)
            content_parts.append(
                compact_html(
                    f"""
                <div class="lia-email__recipients-section">
                    <div class="lia-email__recipients-header">
                        {icon(Icons.PERSON, size="sm")}
                        <span>{escape_html(to_label)}</span>
                    </div>
                    <div class="lia-email__recipients-list">{to_list_html}</div>
                </div>
            """
                )
            )

        # Add CC recipients section - with icon, aligned with title
        cc_recipients = data.get("cc", [])
        if cc_recipients:
            cc_label = V3Messages.get_cc(ctx.language)
            cc_list_html = self._render_recipients_vertical(cc_recipients)
            content_parts.append(
                compact_html(
                    f"""
                <div class="lia-email__recipients-section">
                    <div class="lia-email__recipients-header">
                        {icon(Icons.PERSON, size="sm")}
                        <span>{escape_html(cc_label)}</span>
                    </div>
                    <div class="lia-email__recipients-list">{cc_list_html}</div>
                </div>
            """
                )
            )

        # Add body content AFTER recipients
        if body:
            # Convert HTML to clean text with preserved links in Markdown format
            body_text, is_truncated = format_email_body(
                body,
                max_length=settings.emails_body_max_length,
                preserve_links=True,
            )

            # Read more link (provider-aware: Gmail, Outlook, etc.)
            read_more_html = ""
            if is_truncated and url:
                provider = data.get("_provider", "")
                read_more_label = V3Messages.get_read_more(ctx.language, provider)
                read_more_html = (
                    f'<a href="{escape_html(url)}" class="lia-email__read-more" target="_blank" rel="noopener">'
                    f"{escape_html(read_more_label)} {icon(Icons.OPEN_IN_NEW)}"
                    f"</a>"
                )

            # Format body: convert Markdown links to HTML, preserve line breaks
            url_threshold = settings.emails_url_shorten_threshold
            link_label = V3Messages.get_link(ctx.language)
            body_lines = body_text.split("\n")
            body_formatted = "<br>".join(
                markdown_links_to_html(line, url_threshold, link_label) for line in body_lines
            )

            # Body content inside responsive container with header
            email_content_label = V3Messages.get_email_content(ctx.language)
            content_parts.append(
                compact_html(
                    f"""
                <div class="lia-email__body-panel">
                    <div class="lia-email__body-header">
                        {icon(Icons.DESCRIPTION)}
                        <span>{email_content_label}</span>
                    </div>
                    <div class="lia-email__body">{body_formatted}</div>
                    {read_more_html}
                </div>
            """
                )
            )

        # If we have content, wrap in collapsible
        if content_parts:
            see_more_label = V3Messages.get_see_more(ctx.language)
            return render_collapsible(
                trigger_text=see_more_label,
                content_html="".join(content_parts),
                initially_open=False,
                language=ctx.language,
            )

        elif snippet:
            return f'<p class="lia-email__snippet">{escape_html(truncate(snippet, 200))}</p>'

        return ""

    def _render_recipients_vertical(self, recipients: list[Any] | Any, max_count: int = 10) -> str:
        """Render recipients as a vertical list (one per line), limited to max_count.

        Each recipient is rendered as a mailto: link.
        """
        if not recipients:
            return ""

        if not isinstance(recipients, list):
            recipients = [recipients]

        lines = []
        for recipient in recipients[:max_count]:
            display_name = self._format_recipient(recipient)
            email = self._extract_recipient_email(recipient)
            if display_name:
                if email:
                    lines.append(
                        f'<div class="lia-email__recipient-item"><a href="mailto:{escape_html(email)}">{escape_html(display_name)}</a></div>'
                    )
                else:
                    lines.append(
                        f'<div class="lia-email__recipient-item">{escape_html(display_name)}</div>'
                    )

        # Add ellipsis if truncated
        if len(recipients) > max_count:
            remaining = len(recipients) - max_count
            lines.append(
                f'<div class="lia-email__recipient-item lia-email__recipient-more">... (+{remaining})</div>'
            )

        return "".join(lines)

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
