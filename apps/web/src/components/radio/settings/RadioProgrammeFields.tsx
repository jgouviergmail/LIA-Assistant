'use client';

/**
 * How often each programme the listener may tune comes back, and what each one
 * is about. The opening and the sign-off belong to the station and are never
 * offered (the API publishes the tunable formats only); the figures a
 * description states are the ones the API publishes, never retyped here.
 */
import {
  BookOpen,
  FileText,
  Hash,
  ListMusic,
  MessagesSquare,
  MessageCircle,
  Newspaper,
  PenLine,
  Radio,
  Search,
  Zap,
  type LucideIcon,
} from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useTranslation } from '@/i18n/client';
import { withFrequency } from '@/lib/radio/preferences';

import type { RadioFieldsProps } from './fields';

const FORMAT_ICONS: Record<string, LucideIcon> = {
  journal: BookOpen,
  headlines: ListMusic,
  bulletin: Newspaper,
  brief: Zap,
  analysis: Search,
  column: PenLine,
  number: Hash,
  dossier: FileText,
  debate: MessagesSquare,
  discussion: MessageCircle,
};

export function RadioProgrammeFields({ lng, options, preferences, onChange }: RadioFieldsProps) {
  const { t } = useTranslation(lng);
  return (
    <Disclosure
      icon={ListMusic}
      title={t('radio.settings.programmes.title')}
      description={t('radio.settings.programmes.summary')}
    >
      <div className="space-y-4">
        <p className="text-xs text-muted-foreground">
          {t('radio.settings.programmes.description')}
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          {options.formats.map(item => {
            const Icon = FORMAT_ICONS[item.format] ?? Radio;
            const id = `radio-frequency-${item.format}`;
            const hintId = `${id}-hint`;
            const choose = (value: string) => {
              const frequency = options.frequencies.find(candidate => candidate === value);
              if (frequency) onChange(withFrequency(preferences, item.format, frequency));
            };
            return (
              <div key={item.format} className="flex h-full flex-col rounded-lg border p-4">
                <div className="flex items-start gap-2.5">
                  <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                  <div className="min-w-0 space-y-1">
                    <Label htmlFor={id}>{t(item.label_key)}</Label>
                    <p id={hintId} className="text-xs leading-5 text-muted-foreground">
                      {t(`radio.settings.programmes.hints.${item.format}`, {
                        stories: item.stories_max ?? 0,
                        noon: options.noon_from_hour,
                        evening: options.evening_from_hour,
                      })}
                    </p>
                  </div>
                </div>
                <div className="mt-auto pt-4">
                  <Select
                    value={preferences.frequencies[item.format] ?? item.default_frequency}
                    onValueChange={choose}
                  >
                    <SelectTrigger id={id} className="w-full" aria-describedby={hintId}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {options.frequencies.map(frequency => (
                        <SelectItem key={frequency} value={frequency}>
                          {t(`radio.settings.frequency.${frequency}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Disclosure>
  );
}
