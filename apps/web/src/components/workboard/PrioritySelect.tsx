'use client';
/**
 * A ticket's priority, as a control (ADR-276, D81).
 *
 * Four ranked marks — a double chevron, a chevron, a dash, a chevron down —
 * each in the ink of the edge that ranks the card, so a list item and the card
 * it describes never disagree. ONE list for the creation form, the detail
 * panel and the filter bar: the filter alone asks for « any priority » first,
 * and Radix refuses an item whose value is empty, so that entry travels as
 * `PRIORITY_ANY` and the filter turns it back into « no filter ».
 */
import { useTranslation } from 'react-i18next';

import { GlyphSelect } from '@/components/workboard/GlyphSelect';
import { anyIcon, priorityIcon } from '@/lib/workboard/icons';
import { TICKET_PRIORITIES } from '@/types/workboard';

/** The filter's « any priority » entry — never sent to the API. */
export const PRIORITY_ANY = 'any';

export interface PrioritySelectProps {
  value: string;
  label: string;
  onChange: (priority: string) => void;
  /** Offer « any priority » first, as `PRIORITY_ANY`. */
  withAny?: boolean;
  /** Visually hide the label; it stays in the accessibility tree. */
  hideLabel?: boolean;
  id?: string;
  className?: string;
  /** The family's glyph, drawn in the visible label. */
  labelGlyph?: React.ReactNode;
}

const GLYPH = 'h-3.5 w-3.5 shrink-0';
const ANY_GLYPH = 'h-3.5 w-3.5 shrink-0 text-primary';

export function PrioritySelect({
  value,
  label,
  onChange,
  withAny = false,
  hideLabel = true,
  id,
  className,
  labelGlyph,
}: PrioritySelectProps) {
  const { t } = useTranslation();
  const items = [
    ...(withAny
      ? [
          {
            value: PRIORITY_ANY,
            glyph: anyIcon(ANY_GLYPH),
            text: t('workboard.filters.priority_any'),
          },
        ]
      : []),
    ...TICKET_PRIORITIES.map(priority => ({
      value: priority,
      glyph: priorityIcon(priority, GLYPH),
      text: t(`workboard.priority.${priority}`),
    })),
  ];
  return (
    <GlyphSelect
      id={id}
      label={label}
      labelGlyph={labelGlyph}
      hideLabel={hideLabel}
      value={value}
      items={items}
      className={className}
      onChange={onChange}
    />
  );
}
