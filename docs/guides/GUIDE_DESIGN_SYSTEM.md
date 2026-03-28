# Design System v4 — HTML Card Components

> Reference guide for the standardized component library used by all 14 HTML cards in LIA.

**Version**: 4.0
**Last updated**: 2026-03-28
**Status**: Active

---

## Architecture Overview

Every card is assembled from the **same reusable components**. Only colors and data change — the structure is identical across all cards.

```
lia-card (container + optional left-border status)
  [lia-card-hero]       Full-width image (place photo, route map)
  lia-card-top          Illustration 42px + title (border-bottom separator)
  lia-chip-row          Chips metadata (optional border separators)
  lia-d-row * N         Icon + text lines (address, phone, etc.)
  [lia-att-row]         Stacked attendee avatars
  lia-collapsible       "Voir plus" expandable section
    lia-sec             Mini-illustration 28px + section label (border-top)
    content             d-item, desc-block, kv-rows, review, part-list...
    lia-sec             Another section
    ...
```

### Design Principles

- **Zero domain-specific classes** in v4 components — no `lia-event__header`, `lia-email__header-row`, etc.
- **Reusable everywhere** — any new card uses the same building blocks
- **Dark mode native** — every component has `.dark` overrides using CSS custom properties
- **Responsive** — container queries `@container card (max-width: 430px)` handle mobile adaptation
- **i18n ready** — all text via `V3Messages` (6 languages: fr, en, de, es, it, zh)
- **Accessible** — semantic HTML5 (`<details>/<summary>`), ARIA attributes on icons

---

## CSS Components

**File**: `apps/web/src/styles/lia-components.css` (section "DESIGN SYSTEM v4")

### Structure Components

| Component | CSS Class | Size | Purpose |
|-----------|-----------|------|---------|
| Card top | `.lia-card-top` | — | Flex row: illus + title, `border-bottom` separator |
| Illustration | `.lia-illus` | 42px | Square rounded (12px radius), gradient bg, filled icon 22px |
| Mini illustration | `.lia-illus-sm` | 28px | For section headers in collapsible content |
| Hero image | `.lia-card-hero` | Full width | Photo/map at top of card, `border-radius` top corners |
| Chip row | `.lia-chip-row` | — | Flex wrap container for chips |
| Section header | `.lia-sec` | — | Mini-illus + uppercase label, `border-top` separator |

### Data Components

| Component | CSS Class | Purpose |
|-----------|-----------|---------|
| Chip | `.lia-chip` | Inline metadata tag with icon + text + border |
| Detail row | `.lia-d-row` | Icon + text in main card body |
| Detail item | `.lia-d-item` | Icon + text in collapsible (same spacing as d-row) |
| Description block | `.lia-desc-block` | Subtle background with optional left border |
| Type badge | `.lia-tbadge` | Small colored label (work/home/mobile) |
| Attendee row | `.lia-att-row` | Stacked avatar circles + count label |
| Participant list | `.lia-part-list` | Vertical list: status icon + name + email |
| Source link | `.lia-src-link` | Icon + clickable URL, one per line |
| KV rows | `.lia-kv-rows` | Generic key-value grid (hours, MCP fields) |
| Review | `.lia-review` | Author + date + stars + text |
| Raw block | `.lia-raw-block` | Monospace for JSON/raw text |
| File meta | `.lia-file-meta` | Small icon (12px) + metadata text |

### Color Variants

#### Illustration colors (`.lia-illus--{color}`)

| Color | Light mode | Dark mode | Used for |
|-------|-----------|-----------|----------|
| `green` | `#dcfce7 → #bbf7d0` | `rgba(52,211,153,0.15)` | Accepted events, open places, completed tasks, normal traffic |
| `red` | `#fee2e2 → #fecaca` | `rgba(248,113,113,0.15)` | Declined events, closed places, overdue tasks, heavy traffic |
| `amber` | `#fef3c7 → #fde68a` | `rgba(251,191,36,0.15)` | Pending events, reminders, moderate traffic |
| `blue` | `#dbeafe → #bfdbfe` | `rgba(59,130,246,0.15)` | Web search, files (doc) |
| `indigo` | `#e0e7ff → #c7d2fe` | `rgba(99,102,241,0.15)` | Section headers, search sections |
| `purple` | `#ede9fe → #ddd6fe` | `rgba(124,58,237,0.15)` | Wikipedia articles |
| `teal` | `#ccfbf1 → #99f6e4` | `rgba(13,148,136,0.15)` | MCP results |
| `orange` | `#ffedd5 → #fed7aa` | `rgba(234,88,12,0.15)` | File (slides/pptx) |
| `gray` | `#f3f4f6 → #e5e7eb` | `rgba(107,114,128,0.15)` | Read emails, default |

#### Chip variants (`.lia-chip--{variant}`)

| Variant | Purpose | Example |
|---------|---------|---------|
| `green` | Success/positive | Open, completed, normal traffic |
| `amber` | Warning | Due date, pending |
| `red` | Danger | Overdue, closed, heavy traffic |
| `indigo` | Information | Date, type, thread count |
| `time` | Time display | `14:00 - 15:30` (bold green) |
| `stars` | Star rating | `★★★★☆ 4.3 (245)` |
| `thread` | Thread count | Thread messages |
| `attach` | Attachments | File attachments |
| `allday` | All-day event | "All day" |

#### Type badge variants (`.lia-tbadge--{variant}`)

| Variant | Color | Used for |
|---------|-------|----------|
| `work` | Indigo | Work email, work phone, work address |
| `home` | Green | Home email, home phone |
| `mobile` | Amber | Mobile phone |
| `other` | Gray | Other/unknown types, relation types |

### Separator Rules

| Location | Separator | CSS property |
|----------|-----------|-------------|
| Under card-top | `border-bottom` on `.lia-card-top` | `1px solid var(--lia-border)` |
| Under chip-row | Modifier class `.lia-chip-row--sep-bottom` | `border-bottom` |
| Above chip-row | Modifier class `.lia-chip-row--sep-top` | `border-top` |
| Above section header | Built into `.lia-sec` | `border-top` (except `.lia-sec--first`) |
| Above "Voir plus" | `<hr>` from `render_collapsible()` | Controlled by `with_separator` param |

**Color**: `var(--lia-border)` = `#e5e7eb` (light) / `#374151` (dark)

### Responsive Behavior

Container query: `@container card (max-width: 430px)`

| Component | Mobile adaptation |
|-----------|-------------------|
| `.lia-chip` | Smaller font (0.6875rem), reduced padding |
| `.lia-att-av` | 20px instead of 24px |
| `.lia-d-row`, `.lia-d-item` | Smaller font (--lia-text-xs) |
| `.lia-part-list` | Reduced left margin |
| `.lia-card-hero img` | Max height 140px |

---

## Python Helpers

**File**: `apps/api/src/domains/agents/display/components/base.py`

### Structure Helpers

```python
render_card_top(icon_name, illus_color, title_html, badges_html="", subtitle_html="")
render_card_hero(image_url, alt_text="")
render_chip(text, variant="", icon_name="")
render_chip_stars(rating, count=0)
render_chip_row(chips_html, separator_pos="")  # "top", "bottom", "both", ""
render_section_header(label, icon_name, illus_color="indigo", first=False)
render_d_row(icon_name, content_html, icon_style="")
render_d_item(icon_name, content_html, icon_style="")
```

### Content Helpers

```python
render_desc_block(content_html, with_border=True)
render_att_row(attendees, max_shown=4, label_text="")
render_part_list(participants, max_shown=10)
render_type_badge(label, variant="other")
render_src_link(url, domain="")
render_kv_rows(pairs)           # list[tuple[str, str]]
render_review(author, time_text, rating, text)
render_raw_block(content)
render_file_meta(icon_name, text)
```

### Modified Existing Helper

```python
render_collapsible(trigger_text, content_html, initially_open=False, language="fr", with_separator=True)
# with_separator=False when the preceding element already provides a visual separator
```

---

## Card Inventory

### Cards with left-border status

| Card | Status colors | Illustration icon |
|------|--------------|-------------------|
| EventCard | green (accepted), amber (pending), red (declined) | `event_available` / `pending` / `event_busy` |
| EmailCard | green (unread), gray (read), amber (important), red (urgent) | Initials in illus |
| PlaceCard | green (open), red (closed) | Place type icon (`restaurant`, `coffee`, etc.) |
| RouteCard | green (normal), amber (moderate), red (heavy traffic) | Travel mode icon (`directions_car`, etc.) |
| TaskItem | green (completed), amber (pending), red (overdue) | `check_circle` / `radio_button_unchecked` / `error` |
| ReminderCard | amber (normal), red (imminent) | `notifications` / `notifications_active` |

### Cards without left-border

| Card | Illustration | Color |
|------|-------------|-------|
| ContactCard | Photo or initials | `indigo` |
| WeatherCard | Weather icon (large, existing layout preserved) | Condition-based |
| FileItem | File type icon | Type-based (blue/green/red/amber/purple) |
| ArticleCard | `menu_book` | `purple` |
| WebSearchCard | `travel_explore` | `blue` |
| SearchResultCard | `search` | `blue` |
| McpResultCard | `extension` | `teal` |

---

## Creating a New Card

1. **Create the component** in `apps/api/src/domains/agents/display/components/new_card.py`
2. **Extend `BaseComponent`** and implement `render()`
3. **Use v4 helpers** — never create card-specific CSS classes:

```python
from src.domains.agents.display.components.base import (
    render_card_top, render_chip, render_chip_row,
    render_d_row, render_collapsible, render_section_header,
    # ... other helpers as needed
)

def _render_card(self, ..., ctx: RenderContext) -> str:
    card_top = render_card_top("icon_name", "color", title_html)
    chips = render_chip_row(
        render_chip("value", "variant", "icon") + " " +
        render_chip("value2", "variant2", "icon2"),
        separator_pos="bottom",
    )
    details = render_d_row("location_on", address_link, icon_style="...")

    collapsible = render_collapsible(
        trigger_text=V3Messages.get_see_more(ctx.language),
        content_html=section_content,
        with_separator=False,
    )

    return f'<div class="lia-card {nested_class}">{card_top}{chips}{details}{collapsible}</div>'
```

4. **No new CSS needed** — all styling comes from the shared v4 components
5. **Register** the component in `html_renderer.py`
6. **Test** in light mode, dark mode, desktop and mobile

---

## Files Reference

| File | Purpose |
|------|---------|
| `apps/web/src/styles/lia-components.css` | All CSS (v4 section + existing) |
| `apps/api/src/domains/agents/display/components/base.py` | Python helpers |
| `apps/api/src/domains/agents/display/icons.py` | Material Symbols icon enum + `icon()` helper |
| `apps/api/src/core/i18n_v3.py` | All i18n labels (V3Messages) |
| `docs/prototypes/PLANCHE_FINALE_v4.html` | Visual reference prototype |
