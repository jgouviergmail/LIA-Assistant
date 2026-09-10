'use client';
/**
 * A ticket's column, as a control (ADR-276, D17, D79).
 *
 * The board's drag-and-drop is a pointer gesture; keyboard equivalence is a
 * correctness rule in this repository, not an option. A list gives it for
 * free, and where nothing drags it doubles as the card's status display, so
 * the card carries no badge repeating the column it already sits in.
 *
 * The application's own listbox, no longer a native `<select>` (lot 20):
 * every item wears its column's glyph before its name — the mark the column
 * header and the settings chips already wear — and a native `<option>` holds
 * nothing but text. The native control's other virtue, the platform's picker
 * on a phone, was traded for that at the owner's request; and its stated
 * reason to exist — a portalled listbox fighting the drag sensors for the
 * pointer — no longer applies anywhere this list is drawn: below `lg` no card
 * is a sortable item, and the panel is a dialog.
 *
 * ONE list for the three places a column is chosen — a card, the panel and
 * the phone's column picker (`statuses` and `counts`) — so they can never
 * wear two different marks for one column.
 */
import { useTranslation } from 'react-i18next';

import { GlyphSelect } from '@/components/workboard/GlyphSelect';
import { columnIcon } from '@/lib/workboard/icons';
import { TICKET_STATUSES } from '@/types/workboard';

export interface StatusSelectProps {
  value: string;
  /** The accessible name — a card in a list needs to say WHICH ticket. */
  label: string;
  onChange: (status: string) => void;
  disabled?: boolean;
  className?: string;
  /** Visually hide the label; it stays in the accessibility tree. */
  hideLabel?: boolean;
  id?: string;
  /** The columns offered — every column by default. */
  statuses?: readonly string[];
  /** When given, each item carries its column's EXACT count (ADR-185). */
  counts?: Readonly<Record<string, number>>;
}

/** The column header's glyph, at the size of the line it sits on. */
const GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

export function StatusSelect({
  value,
  label,
  onChange,
  disabled,
  className,
  hideLabel = true,
  id,
  statuses = TICKET_STATUSES,
  counts,
}: StatusSelectProps) {
  const { t } = useTranslation();
  const items = statuses.map(status => {
    const name = t(`workboard.columns.${status}`);
    return {
      value: status,
      glyph: columnIcon(status, GLYPH),
      text: counts ? `${name} (${counts[status] ?? 0})` : name,
    };
  });
  return (
    <GlyphSelect
      id={id}
      label={label}
      hideLabel={hideLabel}
      value={value}
      items={items}
      disabled={disabled}
      className={className}
      onChange={onChange}
    />
  );
}
