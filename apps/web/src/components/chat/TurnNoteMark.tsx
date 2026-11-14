'use client';

/**
 * Said under the person's bubble when the words were added to the answer in
 * progress rather than sent as a turn of their own (ADR-385): the archived row
 * carries `turn_note: true`. Renders nothing otherwise.
 */

import { useTranslation } from 'react-i18next';

import { CornerDownRight } from '@/lib/icons';

export function TurnNoteMark({ metadata }: { metadata?: Record<string, unknown> }) {
  const { t } = useTranslation();
  if (metadata?.turn_note !== true) return null;
  const label = t('chat.message.turn_note');
  return (
    <>
      {' | '}
      <span
        className="inline-flex items-center gap-1 text-primary"
        role="img"
        aria-label={label}
        title={label}
      >
        <CornerDownRight className="inline h-3 w-3" aria-hidden="true" />
      </span>
    </>
  );
}
