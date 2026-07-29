'use client';

/**
 * CardItemActions — the per-item immediate-action chips (QW-24).
 *
 * QW-9 made every briefing item a button that PREFILLS the chat. QW-24 adds
 * named actions that EXECUTE: each chip deep-links to `?intent=`, which the
 * chat page auto-sends through the normal pipeline (ADR-173) — so external
 * writes keep their tool-level HITL cards, and nothing bypasses approval.
 *
 * Rendered as SIBLINGS of the item's main button, never inside it (nested
 * buttons are invalid HTML and unreachable by AT). The aria-label IS the
 * full intent sentence — the name states exactly what the click sends.
 */

import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';

export interface CardItemAction {
  icon: LucideIcon;
  /** Full localized intent — doubles as the accessible name. */
  label: string;
  onSelect: () => void;
}

/** Shared chip classes — reuse for a `trailing` element so it aligns exactly. */
export const CARD_ITEM_ACTION_CLASS =
  'p-1.5 rounded-md text-muted-foreground/70 hover:text-primary hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring transition-colors';

/**
 * The action chips row. `trailing` (e.g. a document's external-open link) is
 * rendered INSIDE the same flex container so every icon shares one gap and one
 * vertical centre line — a sibling with different padding was the misalignment
 * fixed here. Style a trailing element with `CARD_ITEM_ACTION_CLASS` so its box
 * matches the chips.
 */
export function CardItemActions({
  actions,
  trailing,
}: {
  actions: readonly CardItemAction[];
  trailing?: ReactNode;
}) {
  return (
    <span className="flex shrink-0 items-center gap-0.5">
      {actions.map(action => (
        <button
          key={action.label}
          type="button"
          onClick={action.onSelect}
          aria-label={action.label}
          title={action.label}
          className={CARD_ITEM_ACTION_CLASS}
        >
          <action.icon className="h-3.5 w-3.5" aria-hidden="true" />
        </button>
      ))}
      {trailing}
    </span>
  );
}
