'use client';

/**
 * What of the listener's own life the radio may speak of, each source saying
 * what it reads. A source switched off is never READ, not merely left unsaid —
 * which is why this is a switch per source and not a filter on what airs.
 */
import {
  Bell,
  BookOpen,
  Bookmark,
  CalendarDays,
  CalendarHeart,
  Cake,
  CheckCheck,
  CloudSun,
  HeartPulse,
  ListTodo,
  Mail,
  MailCheck,
  MessageCircle,
  MessagesSquare,
  Radio,
  Ticket,
  UserRound,
  Users,
  type LucideIcon,
} from 'lucide-react';

import { Disclosure } from '@/components/ui/disclosure';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import { withSourceHeard } from '@/lib/radio/preferences';

import type { RadioFieldsProps } from './fields';

const SOURCE_ICONS: Record<string, LucideIcon> = {
  agenda: CalendarDays,
  reminders: Bell,
  tasks: ListTodo,
  commitments: CheckCheck,
  tickets: Ticket,
  birthdays: Cake,
  mails: Mail,
  sent_mails: MailCheck,
  actions: Radio,
  weather: CloudSun,
  health: HeartPulse,
  meetings: Users,
  notifications: Bell,
  relations: UserRound,
  spaces: BookOpen,
  bookmarks: Bookmark,
  conversation: MessagesSquare,
};

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
          const Icon = SOURCE_ICONS[source] ?? MessageCircle;
          const id = `radio-source-${source}`;
          const hintId = `${id}-hint`;
          return (
            <li key={source} className="flex items-start justify-between gap-3 rounded-lg border p-3">
              <div className="flex min-w-0 items-start gap-2.5">
                <Icon className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                <div className="min-w-0 space-y-0.5">
                  <Label htmlFor={id}>{t(`radio.settings.source.${source}`)}</Label>
                  <p id={hintId} className="text-xs leading-5 text-muted-foreground">
                    {t(`radio.settings.source_hints.${source}`)}
                  </p>
                </div>
              </div>
              <Switch
                className="shrink-0"
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
