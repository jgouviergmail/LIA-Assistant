'use client';

/**
 * What of the listener's own life the radio may speak of, each source saying
 * what it reads. A source switched off is never READ, not merely left unsaid —
 * which is why this is a switch per source and not a filter on what airs.
 */
import { CalendarHeart } from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import { withSourceHeard } from '@/lib/radio/preferences';

import type { RadioFieldsProps } from './fields';

export function RadioSourceFields({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  return (
    <Disclosure
      icon={CalendarHeart}
      title={t('radio.settings.sources.title')}
      description={t('radio.settings.sources.description')}
    >
      <ul className="grid gap-3 sm:grid-cols-2">
        {options.sources.map(source => {
          const id = `radio-source-${source}`;
          const hintId = `${id}-hint`;
          return (
            <li key={source} className="flex items-start justify-between gap-3">
              <div className="space-y-0.5">
                <Label htmlFor={id}>{t(`radio.settings.source.${source}`)}</Label>
                <p id={hintId} className="text-xs text-muted-foreground">
                  {t(`radio.settings.source_hints.${source}`)}
                </p>
              </div>
              <Switch
                id={id}
                aria-describedby={hintId}
                checked={!preferences.disabled_sources.includes(source)}
                onCheckedChange={heard => onChange(withSourceHeard(preferences, source, heard))}
              />
            </li>
          );
        })}
      </ul>
    </Disclosure>
  );
}
