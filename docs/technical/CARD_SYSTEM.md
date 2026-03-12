# Card System - Unified Design System

> **Version** : 1.0 | **Date** : 2026-01-23

---

## 1. Overview

The LIA card system unifies two previously separate implementations:

1. **React Card Component** (`apps/web/src/components/ui/card.tsx`) - Used in settings, auth, admin pages
2. **LIA CSS Cards** (`apps/web/src/styles/lia-components.css`) - Used for domain cards (email, contact, event, etc.)

Both now share the same **design tokens** for visual consistency.

---

## 2. Design Tokens

All cards use CSS variables from `lia-components.css`:

| Token | Value | Usage |
|-------|-------|-------|
| `--lia-radius-lg` | 14px | Card border radius |
| `--lia-shadow-sm` | `0 1px 2px rgba(0,0,0,0.04)` | Default elevation |
| `--lia-shadow-md` | `0 2px 8px rgba(0,0,0,0.06)` | Elevated cards |
| `--lia-shadow-lg` | `0 4px 16px rgba(0,0,0,0.08)` | Hover state |
| `--lia-space-lg` | 16px | Standard padding |
| `--lia-space-md` | 12px | Mobile padding |

---

## 3. React Card Component

### Import

```typescript
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from '@/components/ui/card';
```

### Variants

#### Visual Variants (`variant`)

| Variant | Description | Classes |
|---------|-------------|---------|
| `default` | Standard card | Shadow small |
| `elevated` | Raised card with hover effect | Shadow medium, hover shadow large |
| `interactive` | Clickable card | Cursor pointer, border highlight on hover |
| `flat` | No shadow | Flat appearance |
| `gradient` | Gradient background | Uses `bg-gradient-card` |

#### Status Variants (`status`)

| Status | Description | Visual |
|--------|-------------|--------|
| `info` | Informational | Blue left border + subtle blue background |
| `success` | Success state | Green left border + subtle green background |
| `warning` | Warning state | Orange left border + subtle orange background |
| `error` | Error state | Red left border + subtle red background |

#### Size Variants (`size`)

| Size | Padding | Use Case |
|------|---------|----------|
| `none` | 0 (default) | When using CardHeader/CardContent |
| `sm` | 12px | Compact cards |
| `md` | 16px | Standard cards |
| `lg` | 24px | Spacious cards |

#### Domain Accents (`domainAccent`)

| Domain | Color Variable |
|--------|---------------|
| `email` | `--lia-email-accent` |
| `contact` | `--lia-contact-accent` |
| `calendar` | `--lia-calendar-accent` |
| `task` | `--lia-task-accent` |
| `place` | `--lia-place-accent` |
| `weather` | `--lia-weather-accent` |
| `drive` | `--lia-drive-accent` |

### Examples

```tsx
// Basic card with content
<Card size="lg">
  <p>Simple content</p>
</Card>

// Card with header structure
<Card>
  <CardHeader>
    <CardTitle>Title</CardTitle>
    <CardDescription>Description</CardDescription>
  </CardHeader>
  <CardContent>Content here</CardContent>
</Card>

// Status card
<Card status="warning" size="md">
  <p>Warning message</p>
</Card>

// Domain-specific card
<Card domainAccent="email" variant="elevated">
  <CardContent>Email content</CardContent>
</Card>
```

---

## 4. CSS Utility Classes

### Card Header Layout

```css
.lia-card__header        /* Flex container: space-between */
.lia-card__header-main   /* Title + subtitle (flex: 1) */
.lia-card__header-end    /* Meta + badges (flex-shrink: 0) */
.lia-card__title         /* Title text styling */
.lia-card__subtitle      /* Subtitle text styling */
.lia-card__meta          /* Meta text (date, count) */
```

### Title Underline Effect

```css
.lia-title-underline     /* Adds gradient underline on hover */
```

Domain-specific gradients are applied automatically when inside `.lia-email`, `.lia-contact`, etc.

**Note:** Legacy domain-specific `::after` rules (e.g., `.lia-contact__name::after`) are deprecated but kept for backward compatibility. New implementations should use `.lia-title-underline` class with the domain wrapper.

### Extended Section

```css
.lia-card-extended       /* Collapsible content area with top border */
```

### Detail Item

```css
.lia-detail-item         /* Icon + text layout for addresses, phones, etc. */
```

### Quote Block

```css
.lia-quote-block         /* Bordered text block for descriptions, bios */
```

### Badges Container

```css
.lia-badges              /* Flexbox wrapper for badge lists */
```

---

## 5. Python Helpers (Backend)

### Import

```python
from src.domains.agents.display.components.base import (
    render_badges,
    render_card_header,
    render_detail_item,
    render_quote_block,
)
```

### render_card_header()

```python
render_card_header(
    title="Meeting Notes",
    url="https://...",
    subtitle="Project Alpha",
    meta="Today",
    badges=[{"text": "Important", "variant": "warning"}]
)
```

### render_detail_item()

```python
render_detail_item("phone", "+33 1 23 45 67 89", url="tel:+33123456789")
render_detail_item("location_on", "123 Main St, Paris")
```

### render_quote_block()

```python
render_quote_block("This is a bio text...")
render_quote_block("Important note", accent_color="var(--lia-warning)")
```

### render_badges()

```python
render_badges([
    {"text": "Important", "variant": "warning"},
    {"text": "3 messages", "variant": "info", "icon": "mail"},
])
```

---

## 6. Responsive Strategy

### Breakpoints

| Name | Width | Description |
|------|-------|-------------|
| Mobile | ≤430px | Compact layout |
| Tablet | 431-768px | Medium layout |
| Desktop | >768px | Full layout |

### Container Queries (Preferred)

Cards use CSS Container Queries for component-level responsiveness:

```css
.lia-card {
  container-type: inline-size;
  container-name: card;
}

@container card (max-width: 400px) {
  .lia-card__header {
    flex-direction: column;
  }
}
```

### Legacy Classes (Deprecated)

The `.lia--mobile`, `.lia--tablet`, `.lia--desktop` classes are deprecated.
New components should use media queries or container queries.

---

## 7. Migration Guide

### From `className="p-6"` to `size="lg"`

```tsx
// Before
<Card className="p-6">Content</Card>

// After
<Card size="lg">Content</Card>
```

### From hardcoded shadows to variants

```tsx
// Before
<Card className="shadow-md hover:shadow-lg">Content</Card>

// After
<Card variant="elevated">Content</Card>
```

### From inline status styling to status variant

```tsx
// Before
<Card className="border-l-4 border-l-warning bg-warning/5">Content</Card>

// After
<Card status="warning">Content</Card>
```

---

## 8. Files Reference

| File | Description |
|------|-------------|
| `apps/web/src/components/ui/card.tsx` | React Card component |
| `apps/web/src/styles/lia-components.css` | CSS utilities and tokens |
| `apps/api/src/domains/agents/display/components/base.py` | Python helpers |

---

## 9. Visual Documentation

Access the design system page at:
```
/dashboard/design-system/cards
```

This page shows all card variants, sizes, and statuses with live examples.
