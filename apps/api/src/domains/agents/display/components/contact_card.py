"""
ContactCard Component - Modern Contact Display v3.0.

Renders contact information with:
- Wrapper for assistant comment + suggested actions
- Avatar with photo or initials
- Name, company, title
- Email/phone with click-to-action
- Collapsible details (addresses, birthday, relations, etc.)
- Action buttons (Call, Email)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.core.i18n_dates import get_month_name
from src.core.i18n_v3 import V3Messages
from src.domains.agents.constants import CONTEXT_DOMAIN_CONTACTS
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    build_directions_url,
    escape_html,
    format_phone,
    phone_for_tel,
    render_collapsible,
    render_d_row,
    render_type_badge,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons, get_relation_icon, icon


class ContactCard(BaseComponent):
    """
    Modern contact card component v3.0.

    Design:
    - Response wrapper with assistant comment zone + actions zone
    - Avatar placeholder with initials or photo
    - Name as primary link
    - Compact metadata row (email, phone, company)
    - Collapsible extended details
    - Action buttons (Call, Email, View)
    """

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
        Render contact as modern card with wrapper.

        Args:
            data: Contact data from Google Contacts API
            ctx: Render context (viewport, language, timezone)
            assistant_comment: Optional comment from assistant above card
            suggested_actions: Optional action buttons below card
            with_wrapper: Whether to wrap with response zones
            is_first_item: If True, add top separator (for list rendering)
            is_last_item: If True, add bottom separator (for list rendering)

        Returns:
            HTML string for the contact card
        """
        # Extract data
        name = self._get_name(data, ctx.language)
        url = self._build_contact_url(data)
        emails = data.get("emailAddresses") or data.get("emails", [])
        phones = data.get("phoneNumbers") or data.get("phones", [])
        organizations = data.get("organizations", [])
        photo_url = self._get_photo_url(data)

        # Get primary email/phone
        primary_email = self._get_primary_value(emails)
        primary_phone = self._get_primary_value(phones)
        company, title = self._get_org_info(organizations)

        # Build default actions if not provided
        if suggested_actions is None:
            suggested_actions = self._build_default_actions(primary_email, primary_phone, url, ctx)

        # Unified render - CSS handles responsive adaptation
        card_html = self._render_card(
            name, url, emails, phones, company, title, photo_url, ctx, data
        )

        # Wrap with response zones if requested
        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain=CONTEXT_DOMAIN_CONTACTS,
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _build_default_actions(
        self,
        email: str,
        phone: str,
        url: str,
        ctx: RenderContext,
    ) -> list[dict[str, str]]:
        """Build default action buttons for contact."""
        actions = []

        # Email action
        if email:
            actions.append(
                {
                    "icon": Icons.EMAIL,
                    "label": V3Messages.get_email_action(ctx.language),
                    "url": f"mailto:{email}",
                }
            )

        # Call action
        if phone:
            actions.append(
                {
                    "icon": Icons.PHONE,
                    "label": V3Messages.get_call(ctx.language),
                    "url": f"tel:{phone_for_tel(phone)}",
                }
            )

        # View in Contacts
        if url:
            actions.append(
                {
                    "icon": Icons.PERSON,
                    "label": V3Messages.get_view_details(ctx.language),
                    "url": url,
                }
            )

        return actions

    def _render_card(
        self,
        name: str,
        url: str,
        emails: list,
        phones: list,
        company: str,
        title: str,
        photo_url: str,
        ctx: RenderContext,
        data: dict[str, Any],
    ) -> str:
        """Unified contact card using Design System v4 components."""
        nested_class = self._nested_class(ctx)

        # --- Card top: avatar (photo or initials) + name + subtitle ---
        name_link = f'<a class="lia-card-top__title" href="{escape_html(url)}" target="_blank">{escape_html(name)}</a>'
        subtitle_parts = []
        if company:
            subtitle_parts.append(escape_html(company))
        if title:
            subtitle_parts.append(escape_html(title))
        subtitle_html = " · ".join(subtitle_parts)
        subtitle_with_icon = (
            f'{icon(Icons.WORK, size="xs")} {subtitle_html}' if subtitle_html else ""
        )

        # Build card-top with photo or initials in the illus slot
        if photo_url:
            illus_html = (
                f'<div class="lia-illus lia-illus--indigo" style="overflow:hidden;padding:0">'
                f'<img src="{escape_html(photo_url)}" alt="" '
                f'style="width:100%;height:100%;object-fit:cover;border-radius:inherit">'
                f"</div>"
            )
        else:
            initials = "".join(word[0].upper() for word in name.split()[:2]) if name else "?"
            illus_html = (
                f'<div class="lia-illus lia-illus--indigo">'
                f'<span style="font-size:var(--lia-text-base);font-weight:600">'
                f"{escape_html(initials)}</span></div>"
            )

        card_top_html = (
            f'<div class="lia-card-top">'
            f"{illus_html}"
            f'<div class="lia-card-top__info">'
            f"{name_link}"
            f'{f"<div class=lia-card-top__subtitle>{subtitle_with_icon}</div>" if subtitle_with_icon else ""}'
            f"</div></div>"
        )

        # --- Details: emails, phones, address, birthday (all left-aligned) ---
        email_html = self._render_email_list_v4(emails, ctx)
        phone_html = self._render_phone_list_v4(phones, ctx)
        address_html = self._render_primary_address_v4(data, ctx)
        birthday_html = self._render_birthday_v4(data, ctx)

        # --- Collapsible extended details ---
        collapsible_html = self._render_collapsible_details(data, ctx)

        return f"""<div class="lia-card lia-contact {nested_class}">
{card_top_html}
{email_html}
{phone_html}
{address_html}
{birthday_html}
{collapsible_html}
</div>"""

    def _render_email_list_v4(self, emails: list, ctx: RenderContext) -> str:
        """Render email addresses using v4 d-row + type badges."""
        if not emails:
            return ""
        items = []
        for e in emails[:3]:
            val = e.get("value") if isinstance(e, dict) else str(e)
            etype = e.get("type", "") if isinstance(e, dict) else ""
            type_label = V3Messages.get_data_type(ctx.language, etype) if etype else ""
            link = f'<a href="mailto:{escape_html(val)}">{escape_html(val)}</a>'
            badge = (
                render_type_badge(type_label, self._type_to_variant(etype)) if type_label else ""
            )
            items.append(render_d_row(Icons.EMAIL, f"{link} {badge}"))
        return "\n".join(items)

    def _render_phone_list_v4(self, phones: list, ctx: RenderContext) -> str:
        """Render phone numbers using v4 d-row + type badges."""
        if not phones:
            return ""
        items = []
        for p in phones[:3]:
            val = p.get("value") if isinstance(p, dict) else str(p)
            ptype = p.get("type", "") if isinstance(p, dict) else ""
            formatted = format_phone(val)
            type_label = V3Messages.get_data_type(ctx.language, ptype) if ptype else ""
            link = f'<a href="tel:{phone_for_tel(val)}">{escape_html(formatted)}</a>'
            badge = (
                render_type_badge(type_label, self._type_to_variant(ptype)) if type_label else ""
            )
            items.append(render_d_row(Icons.PHONE, f"{link} {badge}"))
        return "\n".join(items)

    def _render_primary_address_v4(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render primary address using v4 d-row."""
        addresses = data.get("addresses", [])
        if not addresses:
            return ""
        addr = addresses[0]
        formatted = (
            addr.get("formattedValue") or addr.get("formatted", "")
            if isinstance(addr, dict)
            else str(addr)
        )
        atype = addr.get("type", "") if isinstance(addr, dict) else ""
        if not formatted:
            return ""
        type_label = V3Messages.get_data_type(ctx.language, atype) if atype else ""
        directions_url = build_directions_url(formatted)
        link = (
            f'<a href="{escape_html(directions_url)}" target="_blank">{escape_html(formatted)}</a>'
        )
        badge = render_type_badge(type_label, self._type_to_variant(atype)) if type_label else ""
        return render_d_row(
            Icons.LOCATION,
            f"{link} {badge}",
            icon_style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#ef4444",
        )

    def _render_birthday_v4(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render birthday using v4 d-row."""
        birthdays = data.get("birthdays", [])
        if not birthdays:
            return ""
        bday_str, age = self._format_birthday(
            birthdays[0], include_year=True, language=ctx.language
        )
        if not bday_str:
            return ""
        years_old_label = V3Messages.get_years_old(ctx.language)
        age_str = f" ({age} {years_old_label})" if age else ""
        return render_d_row(
            Icons.BIRTHDAY,
            f"{escape_html(bday_str)}{age_str}",
            icon_style="font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 20;color:#f59e0b",
        )

    @staticmethod
    def _type_to_variant(data_type: str) -> str:
        """Map contact data type to tbadge color variant."""
        dt = data_type.lower() if data_type else ""
        if dt in ("work", "travail", "arbeit", "trabajo", "lavoro"):
            return "work"
        elif dt in ("home", "domicile", "maison", "zuhause", "casa", "hogar"):
            return "home"
        elif dt in ("mobile", "cell", "portable", "mobil", "movil", "cellulare"):
            return "mobile"
        return "other"

    def _render_collapsible_details(self, data: dict[str, Any], ctx: RenderContext) -> str:
        """Render collapsible section using v4 d-row + type badges (same as main card)."""
        detail_sections: list[str] = []

        # Additional addresses (beyond the first)
        addresses = data.get("addresses", [])
        if len(addresses) > 1:
            for addr in addresses[1:3]:
                if isinstance(addr, dict):
                    formatted = addr.get("formattedValue") or addr.get("formatted", "")
                    atype = addr.get("type", "")
                else:
                    formatted = str(addr)
                    atype = ""
                if formatted:
                    type_label = V3Messages.get_data_type(ctx.language, atype) if atype else ""
                    badge = (
                        render_type_badge(type_label, self._type_to_variant(atype))
                        if type_label
                        else ""
                    )
                    detail_sections.append(
                        render_d_row(Icons.LOCATION, f"{escape_html(formatted)} {badge}")
                    )

        # Nicknames
        nicknames = data.get("nicknames", [])
        if nicknames:
            nick_values = []
            for nick in nicknames[:3]:
                val = nick.get("value", "") if isinstance(nick, dict) else str(nick)
                if val:
                    nick_values.append(escape_html(val))
            if nick_values:
                nicknames_label = V3Messages.get_nicknames(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.MOOD, f'{nicknames_label}: {", ".join(nick_values)}')
                )

        # Relations — same d-row + type badge pattern as main card
        relations = data.get("relations", [])
        if relations:
            for rel in relations[:5]:
                if isinstance(rel, dict):
                    person = rel.get("person", "")
                    rtype = rel.get("type", "")
                else:
                    person = str(rel)
                    rtype = ""
                if person:
                    relation_icon = get_relation_icon(rtype)
                    type_label = V3Messages.get_relation_type(ctx.language, rtype) if rtype else ""
                    badge = render_type_badge(type_label, "other") if type_label else ""
                    detail_sections.append(
                        render_d_row(relation_icon, f"{escape_html(person)} {badge}")
                    )

        # Biography/Notes
        biographies = data.get("biographies", [])
        if biographies:
            bio = biographies[0] if biographies else {}
            bio_text = bio.get("value", "") if isinstance(bio, dict) else str(bio)
            if bio_text:
                if len(bio_text) > 150:
                    bio_text = bio_text[:147] + "..."
                detail_sections.append(render_d_row(Icons.NOTE, escape_html(bio_text)))

        # Skills
        skills = data.get("skills", [])
        if skills:
            skill_values = []
            for skill in skills[:5]:
                val = skill.get("value", "") if isinstance(skill, dict) else str(skill)
                if val:
                    skill_values.append(escape_html(val))
            if skill_values:
                skills_label = V3Messages.get_skills(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.SKILLS, f'{skills_label}: {", ".join(skill_values)}')
                )

        # Interests
        interests = data.get("interests", [])
        if interests:
            int_values = []
            for interest in interests[:5]:
                val = interest.get("value", "") if isinstance(interest, dict) else str(interest)
                if val:
                    int_values.append(escape_html(val))
            if int_values:
                interests_label = V3Messages.get_interests(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.INTERESTS, f'{interests_label}: {", ".join(int_values)}')
                )

        # Occupations
        occupations = data.get("occupations", [])
        if occupations:
            occ_values = []
            for occ in occupations[:3]:
                val = occ.get("value", "") if isinstance(occ, dict) else str(occ)
                if val:
                    occ_values.append(escape_html(val))
            if occ_values:
                occupation_label = V3Messages.get_occupation(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.WORK, f'{occupation_label}: {", ".join(occ_values)}')
                )

        # IM clients
        im_clients = data.get("imClients", []) or data.get("im_clients", [])
        if im_clients:
            im_items = []
            for im in im_clients[:3]:
                if isinstance(im, dict):
                    protocol = im.get("protocol", "") or im.get("type", "")
                    username = im.get("username", "") or im.get("value", "")
                    if protocol and username:
                        im_items.append(f"{escape_html(protocol)}: {escape_html(username)}")
            if im_items:
                detail_sections.append(render_d_row(Icons.CHAT, "; ".join(im_items)))

        # Personal events (anniversaries, etc.)
        events = data.get("events", [])
        if events:
            event_items = []
            for event in events[:3]:
                if isinstance(event, dict):
                    etype = event.get("type", "")
                    date_obj = event.get("date", {})
                    if date_obj:
                        day = date_obj.get("day", "")
                        month = date_obj.get("month", "")
                        year = date_obj.get("year", "")
                        if day and month:
                            date_str = self._format_date_components(day, month, year, ctx.language)
                            label = f"{escape_html(etype)}: " if etype else ""
                            event_items.append(f"{label}{date_str}")
            if event_items:
                events_label = V3Messages.get_events(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.EVENT, f'{events_label}: {"; ".join(event_items)}')
                )

        # Locations
        locations = data.get("locations", [])
        if locations:
            loc_items = []
            for loc in locations[:2]:
                if isinstance(loc, dict):
                    ltype = loc.get("type", "")
                    value = loc.get("value", "")
                    if value:
                        type_prefix = f"{escape_html(ltype)}: " if ltype else ""
                        loc_items.append(f"{type_prefix}{escape_html(value)}")
            if loc_items:
                locations_label = V3Messages.get_locations(ctx.language)
                detail_sections.append(
                    render_d_row(Icons.LOCATION, f'{locations_label}: {"; ".join(loc_items)}')
                )

        # Calendar URLs
        calendar_urls = data.get("calendarUrls", []) or data.get("calendar_urls", [])
        if calendar_urls:
            cal_items = []
            calendar_label = V3Messages.get_calendar(ctx.language)
            for cal in calendar_urls[:2]:
                if isinstance(cal, dict):
                    label = cal.get("label", "") or cal.get("type", calendar_label)
                    cal_url = cal.get("url", "")
                    if cal_url:
                        cal_items.append(
                            f'<a href="{escape_html(cal_url)}" target="_blank">'
                            f"{escape_html(label)}</a>"
                        )
            if cal_items:
                detail_sections.append(render_d_row(Icons.DATE_RANGE, "; ".join(cal_items)))

        # Wrap in collapsible
        if detail_sections:
            content_html = "\n".join(detail_sections)
            return render_collapsible(
                trigger_text=V3Messages.get_see_more(ctx.language),
                content_html=content_html,
                initially_open=False,
                language=ctx.language,
                with_separator=False,
            )

        return ""

    def _get_name(self, data: dict, language: str = "fr") -> str:
        """Extract display name from various formats."""
        names = data.get("names")
        if names and isinstance(names, list) and names:
            first = names[0]
            if isinstance(first, dict):
                return first.get("displayName") or first.get("givenName", "")  # type: ignore[no-any-return]
        no_name_fallback = V3Messages.get_no_name(language)
        return data.get("name") or data.get("displayName", no_name_fallback)  # type: ignore[no-any-return]

    def _get_primary_value(self, items: list) -> str:
        """Get first/primary value from list."""
        if not items:
            return ""
        first = items[0]
        if isinstance(first, dict):
            return first.get("value") or first.get("email") or first.get("number", "")  # type: ignore[no-any-return]
        return str(first)

    def _get_org_info(self, organizations: list) -> tuple[str, str]:
        """Extract company and title."""
        if not organizations:
            return "", ""
        org = organizations[0]
        if isinstance(org, dict):
            return org.get("name", ""), org.get("title", "")
        return "", ""

    def _build_contact_url(self, data: dict) -> str:
        """Build a valid Google Contacts URL from contact data."""
        url = data.get("url")
        if url and url.startswith("http"):
            return url  # type: ignore[no-any-return]

        resource_name = data.get("resourceName", "")
        if resource_name:
            if resource_name.startswith("people/"):
                person_id = resource_name[7:]
                return f"https://contacts.google.com/person/{person_id}"
            return f"https://contacts.google.com/person/{resource_name}"

        return ""

    def _get_photo_url(self, data: dict) -> str:
        """
        Extract photo URL from contact data.

        Handles multiple data formats:
        - Direct URL: photoUrl, photo (string)
        - Google People API raw: photos[0].url
        - Processed: photos[0] (string)
        - Nested in coverPhotos: coverPhotos[0].url

        Note: Google People API returns photos with 'default' flag when no custom photo.
        We include these as they're still valid avatar URLs.
        """
        # Direct URL fields (from processed data)
        if data.get("photoUrl"):
            return data["photoUrl"]  # type: ignore[no-any-return]
        if data.get("photo") and isinstance(data.get("photo"), str):
            return data["photo"]  # type: ignore[no-any-return]

        # Google People API format: photos array
        photos = data.get("photos", [])
        if photos and isinstance(photos, list):
            photo = photos[0]
            if isinstance(photo, dict):
                # Standard Google API format: {"url": "...", "metadata": {...}}
                url = photo.get("url", "")
                if url:
                    return url  # type: ignore[no-any-return]
            elif isinstance(photo, str):
                # Simplified format: ["url1", "url2"]
                return photo

        # Fallback: coverPhotos (some Google APIs use this)
        cover_photos = data.get("coverPhotos", [])
        if cover_photos and isinstance(cover_photos, list):
            cover = cover_photos[0]
            if isinstance(cover, dict):
                return cover.get("url", "")  # type: ignore[no-any-return]

        return ""

    def _format_birthday(
        self,
        bday: dict | Any,
        include_year: bool = False,
        language: str = "fr",
    ) -> tuple[str, int | None]:
        """Format birthday with optional age calculation."""
        if not isinstance(bday, dict):
            return "", None

        date_obj = bday.get("date", {})
        if not date_obj:
            return "", None

        day = date_obj.get("day")
        month = date_obj.get("month")
        year = date_obj.get("year")

        if not day or not month:
            return "", None

        try:
            day_int = int(day) if not isinstance(day, int) else day
            month_int = int(month) if not isinstance(month, int) else month

            if 1 <= month_int <= 12:
                month_name = get_month_name(month_int, language)

                # Country-specific format
                if language == "en":
                    date_str = f"{month_name} {day_int}"
                elif language == "de":
                    date_str = f"{day_int}. {month_name}"
                elif language == "zh-CN":
                    date_str = f"{month_int}月{day_int}日"
                else:
                    date_str = f"{day_int} {month_name}"

                if include_year and year:
                    if language == "zh-CN":
                        date_str = f"{year}年" + date_str
                    else:
                        date_str += f" {year}"
            else:
                if language == "en":
                    date_str = f"{month_int:02d}/{day_int:02d}"
                elif language == "de":
                    date_str = f"{day_int:02d}.{month_int:02d}"
                else:
                    date_str = f"{day_int:02d}/{month_int:02d}"
                if include_year and year:
                    date_str += f"/{year}"

            # Calculate age
            age = None
            if year:
                try:
                    year_int = int(year) if not isinstance(year, int) else year
                    today = datetime.now()
                    birth_date = datetime(year_int, month_int, day_int)
                    age = today.year - birth_date.year
                    if (today.month, today.day) < (month_int, day_int):
                        age -= 1
                except (ValueError, TypeError):
                    pass

            return date_str, age

        except (ValueError, TypeError):
            return "", None

    def _format_date_components(
        self,
        day: int | str,
        month: int | str,
        year: int | str | None,
        language: str = "fr",
    ) -> str:
        """Format date from day/month/year components with locale conventions."""
        try:
            day_int = int(day) if not isinstance(day, int) else day
            month_int = int(month) if not isinstance(month, int) else month

            # Locale-aware date format
            if language == "en":
                date_str = f"{month_int:02d}/{day_int:02d}"  # MM/DD
            elif language == "de":
                date_str = f"{day_int:02d}.{month_int:02d}"  # DD.MM
            else:
                date_str = f"{day_int:02d}/{month_int:02d}"  # DD/MM (fr, es, it, zh-CN)

            if year:
                date_str += f"/{year}"

            return date_str
        except (ValueError, TypeError):
            # Fallback to raw values
            return f"{day}/{month}" + (f"/{year}" if year else "")
