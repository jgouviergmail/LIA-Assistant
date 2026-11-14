'use client';
/**
 * A ticket's category, as a badge (ADR-276).
 *
 * What every screen OUTSIDE the board shows: on the board a card sits in its
 * lane, and repeating the lane on it would cost a row for a fact already on
 * screen. Elsewhere — the hub, the dashboard, a ticket's steps — the lane is
 * not there to say it.
 *
 * Neutral on purpose: the owner asked for categories told apart by their NAME,
 * never by a colour each (2026-11-11). The `outline` variant is not the grey
 * `secondary` reserved for inactive elements, and the mark wears the theme
 * colour like every other glyph of the board.
 *
 * A ticket filed under nothing shows NO badge — callers render this only when
 * they have a name.
 */
import { useTranslation } from 'react-i18next';

import { Badge } from '@/components/ui/badge';
import { laneIcon } from '@/lib/workboard/icons';
import { cn } from '@/lib/utils';

export interface CategoryBadgeProps {
  /** The category's name, as its owner wrote it. */
  name: string;
  className?: string;
}

export function CategoryBadge({ name, className }: CategoryBadgeProps) {
  const { t } = useTranslation();
  return (
    <Badge
      variant="outline"
      icon={laneIcon(true, 'h-3 w-3 text-primary')}
      className={cn('max-w-full', className)}
      data-testid="category-badge"
    >
      {/* The glyph is decorative; the word « category » is for a reader who
          cannot see it, with the punctuation its language uses. */}
      <span className="sr-only">
        {t('workboard.form.category')}
        {t('workboard.history.separator')}
      </span>
      <span className="min-w-0 break-words">{name}</span>
    </Badge>
  );
}
