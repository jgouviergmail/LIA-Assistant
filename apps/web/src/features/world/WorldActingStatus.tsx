'use client';
import { Bot } from 'lucide-react';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldActingState } from './world-acting';
export function WorldActingStatus({
  lng,
  state = 'idle',
  hidden = false,
}: {
  lng: Language;
  state?: WorldActingState;
  hidden?: boolean;
}) {
  const { t } = useTranslation(lng);
  if (hidden) return null;
  return (
    <p
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      role="status"
      data-world-acting={state}
    >
      <Bot className="size-3.5 shrink-0 text-primary" aria-hidden="true" />
      {t('world.acting.' + state)}
    </p>
  );
}
