'use client';
import { Files, ListTodo } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { PrivateObjectSignal } from './private-signal-projection';
/** Accessible counterparts of the same local object markers, with no private titles. */
export function WorldSignalActions({
  lng,
  signals,
  onSelect,
}: {
  lng: Language;
  signals: readonly PrivateObjectSignal[];
  onSelect?: (propId: string) => boolean;
}) {
  const { t } = useTranslation(lng);
  const counts = new Intl.NumberFormat(lng);
  return (
    <ul className="space-y-2">
      {signals
        .filter(signal => signal.kind !== 'sms' && signal.kind !== 'reminder')
        .map(signal => {
          const name = t('world.signals.' + signal.kind);
          return (
            <li key={signal.propId}>
              <Button
                variant="outline"
                className="min-h-11 w-full justify-start whitespace-normal"
                disabled={!onSelect}
                onClick={() => onSelect?.(signal.propId)}
              >
                {signal.kind === 'workboard' ? (
                  <ListTodo className="size-4 text-primary" aria-hidden="true" />
                ) : (
                  <Files className="size-4 text-primary" aria-hidden="true" />
                )}
                {name} ·{' '}
                {signal.status === 'unavailable' || signal.count === null
                  ? t('world.signals.unavailable')
                  : counts.format(signal.count)}
              </Button>
            </li>
          );
        })}
    </ul>
  );
}
