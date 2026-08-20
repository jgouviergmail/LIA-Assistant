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
 * Every section is folded on arrival and UNMOUNTED while folded, so no page of
 * rows is ever fetched for a section nobody opened.
 *
 * The badges are the exception, and deliberately so: a badge on a folded block
 * exists to be CHOSEN from, and it said "—" until the section was opened —
 * the one number that decides whether to open a section could only be had by
 * opening it. The five totals therefore come from ONE count read at mount
 * (`useHubCounts`), aggregates over indexed columns rather than rows. The
 * page, with its joins, still waits for the fold.
 */

import { useState } from 'react';
import Link from 'next/link';
import { Bell, CalendarClock, History, Lightbulb, MessageSquare, Sparkles, Star } from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { HeartbeatHistory } from '@/components/settings/HeartbeatHistory';
import { InterestNotificationHistory } from '@/components/settings/InterestNotificationHistory';
import { HubSection, type HubSectionProps } from '@/components/notifications/HubSection';
import { OpenOffersList } from '@/components/notifications/OpenOffersList';
import { PendingRemindersList } from '@/components/notifications/PendingRemindersList';
import { RelayedMessagesList } from '@/components/notifications/RelayedMessagesList';
import { ScheduledActionsList } from '@/components/notifications/ScheduledActionsList';
import { Button } from '@/components/ui/button';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useHubCounts, type HubCounts } from '@/hooks/useHubCounts';
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
  // ONE read for the five badges, so a folded section can be chosen from
  // rather than opened to find out whether it holds anything.
  const { counts } = useHubCounts();

  // One open-state per section: `SettingsDisclosure` unmounts its children
  // when closed, and these flags are what gate each query.
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const isOpen = (key: string) => Boolean(open[key]);
  const track = (key: string) => (value: boolean) =>
    setOpen(previous => ({ ...previous, [key]: value }));

  // Proposals inbox (Lot 5-C2): undecided missed-routine offers. Same
  // fold-gated read as every section; the flag gate mirrors the backend
  // (offers only exist when heartbeat runs).
  const offers = usePagedSection<
    { notifications: HeartbeatNotification[]; total: number },
    HeartbeatNotification
  >({
    path: '/heartbeat/offers',
    selectItems: payload => payload.notifications,
    selectTotal: payload => payload.total,
    enabled: isOpen('offers') && Boolean(config?.features?.heartbeat_enabled),
  });

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

  return { config, counts, track, offers, peers, proactive, interests, reminders, scheduled };
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
  onOpenChange: (open: boolean) => void,
  /** The hub's own count, known before the section is ever opened. */
  knownTotal: number | undefined
) {
  return {
    title: t(`notifications_hub.sections.${key}.title`),
    subtitle: t(`notifications_hub.sections.${key}.subtitle`),
    emptyLabel: t(`notifications_hub.sections.${key}.empty`),
    errorLabel: t(`notifications_hub.sections.${key}.error`),
    // The section's own total once it has data — it is the one that follows a
    // deletion — and the hub's count until then. Two sources for one figure
    // would be a contradiction; this is one figure with two moments.
    total: section.items === undefined ? knownTotal : section.total,
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

/** The proposals section (Lot 5-C2), extracted so the hub component stays
 * under the CC ratchet: the flag gate and the rows live here. */
function ProposalsHubSection({
  enabled,
  section,
  offers,
  lng,
  locale,
}: {
  enabled: boolean;
  section: Omit<HubSectionProps, 'icon' | 'children'>;
  offers: PagedSection<HeartbeatNotification>;
  lng: string;
  locale: string;
}) {
  if (!enabled) return null;
  return (
    <HubSection icon={Lightbulb} {...section}>
      <OpenOffersList
        offers={offers.items ?? []}
        lng={lng}
        locale={locale}
        onDecided={offers.refetch}
      />
    </HubSection>
  );
}

export function NotificationsHub({ lng }: { lng: string }) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);
  const { config, counts, track, offers, peers, proactive, interests, reminders, scheduled } =
    useHubSections();
  const shell = <TItem,>(key: string, section: PagedSection<TItem>, countKey: keyof HubCounts) =>
    sectionShell(key, section, t, track(key), counts?.[countKey]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
            <Bell className="h-7 w-7 text-primary" aria-hidden="true" />
            {t('notifications_hub.title')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('notifications_hub.subtitle')}</p>
        </div>
        {/* Door to the merged activity timeline (Lot 1-A1). The hub answers
            "what reached me?"; the timeline answers "what did LIA do?" —
            siblings, so the door lives at the same altitude as the title.
            Hub-shortcut altitude (ADR-207): solid themed CTA; a real anchor
            via asChild keeps middle-click and open-in-new-tab. */}
        {config?.features?.activity_timeline_enabled && (
          <Button asChild variant="default" size="sm">
            <Link href={`/${lng}/dashboard/activity`}>
              <History className="h-4 w-4" aria-hidden="true" />
              {t('activity.hub_cta')}
            </Link>
          </Button>
        )}
      </div>

      <div className="space-y-2">
        {/* Proposals first: a to-decide set outranks the histories below —
            the reader can ACT here, everywhere else they can only read. */}
        <ProposalsHubSection
          enabled={Boolean(config?.features?.heartbeat_enabled)}
          section={shell('offers', offers, 'offers')}
          offers={offers}
          lng={lng}
          locale={locale}
        />

        {config?.features?.peers_enabled && (
          <HubSection icon={MessageSquare} {...shell('peer_messages', peers, 'peer_messages')}>
            <RelayedMessagesList messages={peers.items ?? []} locale={locale} />
          </HubSection>
        )}

        {config?.features?.heartbeat_enabled && (
          <HubSection icon={Sparkles} {...shell('proactive', proactive, 'proactive')}>
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

        <HubSection icon={Star} {...shell('interests', interests, 'interests')}>
          <InterestNotificationHistory
            notifications={interests.items}
            total={interests.total}
            firstLoad={false}
            loading={interests.loading}
            error={null}
            locale={locale}
          />
        </HubSection>

        <HubSection icon={Bell} {...shell('reminders', reminders, 'reminders')}>
          <PendingRemindersList reminders={reminders.items ?? []} locale={locale} />
        </HubSection>

        <HubSection icon={CalendarClock} {...shell('scheduled', scheduled, 'scheduled')}>
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
              {/* `asChild`: a real anchor keeps middle-click, open-in-new-tab
                  and the "link" role, while the palette, the hover and the AA
                  contrast come from the design system rather than from classes
                  written here that nothing checks. SOLID (ADR-207, owner
                  arbitration 2026-08-05): these shortcuts are the hub's CTAs,
                  and a CTA takes the filled primary everywhere in the app. */}
              <Button asChild variant="default" size="sm" className="min-h-11">
                <Link href={settingsSectionHref(lng, token)}>
                  {/* Named after the DESTINATION, not after the hub section:
                    the same words twice on one page, meaning two different
                    things, is how a reader loses track of where a link goes. */}
                  {t(`notifications_hub.advanced_links.${key}`)}
                </Link>
              </Button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
