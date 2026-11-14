'use client';
/**
 * A ticket's category, as a control (ADR-276).
 *
 * The third vocabulary of the board's one list (`GlyphSelect`), beside the
 * column and the holder: where a card cannot be dragged into another lane — a
 * phone, the detail panel, the creation form — this list is how a ticket is
 * filed. Its items are the reader's OWN categories and « no category »: a
 * ticket may only be filed under a category of its owner, so somebody else's
 * lane is never offered — the server would refuse it.
 *
 * `null` is the value of « filed under nothing ». The listbox underneath
 * refuses an empty value, so the sentinel stays inside this component and
 * never reaches a caller.
 */
import { useTranslation } from 'react-i18next';

import { GlyphSelect } from '@/components/workboard/GlyphSelect';
import { laneIcon } from '@/lib/workboard/icons';
import type { CategoryOption } from '@/types/workboard';

/** The listbox's value for « no category » — never seen outside this file. */
const NONE = 'none';

/** A lane's mark on an item of the list, at the size of the line it sits on. */
const GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

export interface CategorySelectProps {
  /** The category the ticket is filed under; null for none. */
  value: string | null;
  /** The reader's own categories, in their order. */
  categories: readonly CategoryOption[];
  /** The accessible name — a card in a list needs to say WHICH ticket. */
  label: string;
  onChange: (categoryId: string | null) => void;
  disabled?: boolean;
  className?: string;
  /** Visually hide the label; it stays in the accessibility tree. */
  hideLabel?: boolean;
  /** The family's glyph, drawn in the visible label. */
  labelGlyph?: React.ReactNode;
  id?: string;
}

export function CategorySelect({
  value,
  categories,
  label,
  onChange,
  disabled,
  className,
  hideLabel = true,
  labelGlyph,
  id,
}: CategorySelectProps) {
  const { t } = useTranslation();
  // A category that is not among the reader's own — deleted a moment ago —
  // reads as « none », which is where the server is about to put the ticket.
  const selected = categories.some(category => category.id === value) ? value : null;
  const items = [
    { value: NONE, glyph: laneIcon(false, GLYPH), text: t('workboard.categories.none') },
    ...categories.map(category => ({
      value: category.id,
      glyph: laneIcon(true, GLYPH),
      text: category.name,
    })),
  ];
  return (
    <GlyphSelect
      id={id}
      label={label}
      labelGlyph={labelGlyph}
      hideLabel={hideLabel}
      value={selected ?? NONE}
      items={items}
      disabled={disabled}
      className={className}
      onChange={chosen => onChange(chosen === NONE ? null : chosen)}
    />
  );
}
