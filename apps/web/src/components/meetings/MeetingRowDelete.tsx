'use client';

import { useEffect, useRef, type RefObject } from 'react';
import { Trash2 } from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

/** One explicit click deletes one row; removing its trigger restores a stable heading. */
export function MeetingRowDelete({
  lng,
  title,
  unavailable,
  disabled,
  busy,
  onDelete,
  focusTarget,
}: {
  lng: Language;
  title: string;
  unavailable: boolean;
  disabled: boolean;
  busy: boolean;
  onDelete: () => void;
  focusTarget: RefObject<HTMLHeadingElement | null>;
}) {
  const { t } = useTranslation(lng);
  const returnTarget = useRef<HTMLElement | null>(null);
  useEffect(
    () => () => {
      const target = returnTarget.current;
      queueMicrotask(() => {
        if (target?.isConnected && document.activeElement === document.body) target.focus();
      });
    },
    []
  );
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="h-11 w-11 shrink-0 text-destructive hover:text-destructive"
      aria-label={`${t('common.delete')} · ${title}`}
      title={unavailable ? t('meetings.list.not_deletable') : t('common.delete')}
      aria-disabled={disabled || unavailable}
      aria-busy={busy}
      onClick={() => {
        if (disabled || unavailable) return;
        returnTarget.current = focusTarget.current;
        onDelete();
      }}
    >
      <Trash2 className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}
