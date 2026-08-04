'use client';

/**
 * The notifications hub — one page for everything LIA sends, and everything
 * still to come.
 *
 * Those five things lived in four different settings sections (device
 * notifications, proactivity, interests, channels) plus the chat itself, so
 * "what reached me?" had no single answer. The settings keep their detailed
 * controls — this page reads, it never tunes — and every section links back to
 * the one that owns it.
 *
 * **The five are NOT of the same nature, and the subtitles say so.** Relayed
 * messages, proactive notifications and interest notifications are things that
 * ALREADY reached the reader. Reminders and routines are things that WILL:
 * a reminder is deleted the instant it fires, so there is no history of it to
 * show, and a reader looking for one would find an empty list with no
 * explanation. The line under each title states which of the two it is
 * (owner arbitration 2026-08-03: five flat sections, no visual grouping).
 *
 * Every section is folded on arrival and unmounted while folded, so the page
 * costs ZERO requests until the reader opens something.
 */

import { useState } from 'react';
import Link from 'next/link';
import { Bell, CalendarClock, MessageSquare, Sparkles, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { HeartbeatHistory } from '@/components/settings/HeartbeatHistory';
import { InterestNotificationHistory } from '@/components/settings/InterestNotificationHistory';
import { HubSection } from '@/components/notifications/HubSection';
import { PendingRemindersList } from '@/components/notifications/PendingRemindersList';
import { RelayedMessagesList } from '@/components/notifications/RelayedMessagesList';
import { ScheduledActionsList } from '@/components/notifications/ScheduledActionsList';
import { useAppConfig } from '@/hooks/useAppConfig';
import { usePagedSection, type PagedSection } from '@/hooks/usePagedSection';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { settingsSectionHref, type SettingsSectionToken } from '@/lib/settings-sections';
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';
import type { InterestNotification } from '@/hooks/useInterestNotificationHistory';
import type { PendingReminder } from '@/components/notifications/PendingRemindersList';
import type { RelayedMessage } from '@/components/notifications/RelayedMessagesList';
import type { ScheduledActionRow } from '@/components/notifications/ScheduledActionsList';

/** Where each section is tuned in detail — the deep links stay unchanged. */
const ADVANCED: readonly { key: string; token: SettingsSectionToken }[] = [
  { key: 'peer_messages', token: 'peer-connections' },
  { key: 'proactive', token: 'heartbeat' },
  { key: 'interests', token: 'interests' },
  { key: 'scheduled', token: 'scheduled-actions' },
  { key: 'device', token: 'notifications' },
];

/**
 * The five queries, and the fold state that gates them.
 *
 * Extracted from the component so the component reads as what it is — an
 * ORDER of sections — and stays under the shrink-only complexity ratchet.
 */
function useHubSections() {
  const { config } = useAppConfig();

  // One open-state per section: `SettingsDisclosure` unmounts its children
  // when closed, and these flags are what gate each query.
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const isOpen = (key: string) => Boolean(open[key]);
  const track = (key: string) => (value: boolean) =>
    setOpen(previous => ({ ...previous, [key]: value }));

  const peers = usePagedSection<{ messages: RelayedMessage[]; total: number }, RelayedMessage>({
    path: '/peers/messages',
    selectItems: payload => payload.messages,
    selectTotal: payload => payload.total,
    // Gate-keeper (ADR-061): a disabled subsystem is never offered at all.
    enabled: isOpen('peer_messages') && Boolean(config?.features?.peers_enabled),
  });

  const proactive = usePagedSection<
    { notifications: HeartbeatNotification[]; total: number },
    HeartbeatNotification
  >({
    path: '/heartbeat/history',
    selectItems: payload => payload.notifications,
    selectTotal: payload => payload.total,
    enabled: isOpen('proactive') && Boolean(config?.features?.heartbeat_enabled),
  });

  const interests = usePagedSection<
    { notifications: InterestNotification[]; total: number },
    InterestNotification
  >({
    path: '/interests/notifications/history',
    selectItems: payload => payload.notifications,
    selectTotal: payload => payload.total,
    enabled: isOpen('interests'),
  });

  const reminders = usePagedSection<
    { reminders: PendingReminder[]; total: number },
    PendingReminder
  >({
    path: '/reminders',
    selectItems: payload => payload.reminders,
    selectTotal: payload => payload.total,
    enabled: isOpen('reminders'),
  });

  const scheduled = usePagedSection<
    { scheduled_actions: ScheduledActionRow[]; total: number },
    ScheduledActionRow
  >({
    path: '/scheduled-actions',
    selectItems: payload => payload.scheduled_actions,
    selectTotal: payload => payload.total,
    enabled: isOpen('scheduled'),
  });

  return { config, track, peers, proactive, interests, reminders, scheduled };
}

/**
 * Everything `HubSection` needs, derived from one paged section.
 *
 * Generic over the row type so no call site has to erase it — the five
 * sections carry five different shapes and each keeps its own.
 */
function sectionShell<TItem>(
  key: string,
  section: PagedSection<TItem>,
  t: (key: string) => string,
  onOpenChange: (open: boolean) => void
) {
  return {
    title: t(`notifications_hub.sections.${key}.title`),
    subtitle: t(`notifications_hub.sections.${key}.subtitle`),
    emptyLabel: t(`notifications_hub.sections.${key}.empty`),
    errorLabel: t(`notifications_hub.sections.${key}.error`),
    total: section.total,
    page: section.page,
    totalPages: section.totalPages,
    onPageChange: section.setPage,
    firstLoad: section.firstLoad,
    loading: section.loading,
    error: section.error,
    isEmpty: (section.items?.length ?? 0) === 0,
    onOpenChange,
  };
}

export function NotificationsHub({ lng }: { lng: string }) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);
  const { config, track, peers, proactive, interests, reminders, scheduled } = useHubSections();
  const shell = <TItem,>(key: string, section: PagedSection<TItem>) =>
    sectionShell(key, section, t, track(key));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
          <Bell className="h-7 w-7 text-primary" aria-hidden="true" />
          {t('notifications_hub.title')}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('notifications_hub.subtitle')}</p>
      </div>

      <div className="space-y-2">
        {config?.features?.peers_enabled && (
          <HubSection icon={MessageSquare} {...shell('peer_messages', peers)}>
            <RelayedMessagesList messages={peers.items ?? []} locale={locale} />
          </HubSection>
        )}

        {config?.features?.heartbeat_enabled && (
          <HubSection icon={Sparkles} {...shell('proactive', proactive)}>
            {/* The settings card, reused verbatim: two surfaces answering the
                same question must not drift into two visual languages. It owns
                its own count line, so the page below it stays the pager.

                `firstLoad`/`error` are pinned here ON PURPOSE, not forgotten:
                `HubSection` already renders the spinner and the error for this
                section (it receives them through `shell`). Passing them twice
                would draw two spinners and two error messages for one failure. */}
            <HeartbeatHistory
              notifications={proactive.items}
              total={proactive.total}
              firstLoad={false}
              loading={proactive.loading}
              error={null}
              locale={locale}
            />
          </HubSection>
        )}

        <HubSection icon={Star} {...shell('interests', interests)}>
          <InterestNotificationHistory
            notifications={interests.items}
            total={interests.total}
            firstLoad={false}
            loading={interests.loading}
            error={null}
            locale={locale}
          />
        </HubSection>

        <HubSection icon={Bell} {...shell('reminders', reminders)}>
          <PendingRemindersList reminders={reminders.items ?? []} locale={locale} />
        </HubSection>

        <HubSection icon={CalendarClock} {...shell('scheduled', scheduled)}>
          <ScheduledActionsList actions={scheduled.items ?? []} locale={locale} />
        </HubSection>
      </div>

      <section aria-labelledby="hub-advanced" className="rounded-xl border border-border/40 p-4">
        <h2 id="hub-advanced" className="text-sm font-semibold">
          {t('notifications_hub.advanced_title')}
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">{t('notifications_hub.advanced_hint')}</p>
        <ul className="mt-2 flex flex-wrap gap-2" role="list">
          {ADVANCED.map(({ key, token }) => (
            <li key={key}>
              <Link
                href={settingsSectionHref(lng, token)}
                className="inline-flex min-h-11 items-center rounded-lg border border-border/60 px-3 text-xs font-medium text-foreground/90 transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {/* Named after the DESTINATION, not after the hub section:
                    the same words twice on one page, meaning two different
                    things, is how a reader loses track of where a link goes. */}
                {t(`notifications_hub.advanced_links.${key}`)}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
