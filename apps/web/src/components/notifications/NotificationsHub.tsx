'use client';

/** Independent notification sources, grouped by received versus upcoming.
 * Pages stay lazy and independently ordered; no global timeline is inferred
 * from partial pages. Decisions precede both registers. */

import { useRef, useState, type ReactNode } from 'react';
import {
  Bell,
  CalendarClock,
  History,
  LayoutGrid,
  Lightbulb,
  MessageSquare,
  Sparkles,
  Star,
  type LucideIcon,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { SmsHubSection } from '@/components/sms/SmsHubSection';
import { AlertsViewActions } from '@/components/notifications/AlertsViewActions';
import { DiscussionsHubSection } from '@/components/notifications/DiscussionsHubSection';
import { HeartbeatHistory } from '@/components/settings/HeartbeatHistory';
import { InterestNotificationHistory } from '@/components/settings/InterestNotificationHistory';
import { HubSection, type HubSectionProps } from '@/components/notifications/HubSection';
import { NeedsMeList } from '@/components/workboard/NeedsMeList';
import type { TicketRow } from '@/types/workboard';
import { OpenOffersList, useOfferDecisions } from '@/components/notifications/OpenOffersList';
import { PendingRemindersList } from '@/components/notifications/PendingRemindersList';
import { RelayedMessagesList } from '@/components/notifications/RelayedMessagesList';
import { ScheduledActionsList } from '@/components/notifications/ScheduledActionsList';
import { Button } from '@/components/ui/button';
import { SectionHeader } from '@/components/ui/section-header';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useHubCounts, type HubCounts } from '@/hooks/useHubCounts';
import { usePagedSection, type PagedSection } from '@/hooks/usePagedSection';
import { getIntlLocale, type Language } from '@/i18n/settings';
import { publishApplicationResources, type ApplicationResource } from '@/lib/application-resources';
import type { HeartbeatNotification } from '@/hooks/useHeartbeatHistory';
import type { InterestNotification } from '@/hooks/useInterestNotificationHistory';
import type { PendingReminder } from '@/components/notifications/PendingRemindersList';
import type { RelayedMessage } from '@/components/notifications/RelayedMessagesList';
import type { ScheduledActionRow } from '@/components/notifications/ScheduledActionsList';

/** The resources whose readers on this page re-read on the application signal. */
const SIGNALLED_RESOURCES: ReadonlySet<ApplicationResource> = new Set<ApplicationResource>([
  'sms',
  'proactive_discussions',
]);

/**
 * The section queries, and the fold state that gates them.
 *
 * Extracted from the component so the component reads as what it is — an
 * ORDER of sections — and stays under the shrink-only complexity ratchet.
 */
function useHubSections() {
  const { config } = useAppConfig();
  const heartbeatEnabled = Boolean(config?.features?.heartbeat_enabled);
  // ONE read for all badges, so a folded section can be chosen from
  // rather than opened to find out whether it holds anything.
  const {
    counts,
    error: countsError,
    loading: countsLoading,
    refetch: retryCounts,
    ownerId,
  } = useHubCounts();

  // One open-state per section: `Disclosure` unmounts its children
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
    enabled: isOpen('offers') && heartbeatEnabled,
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
    enabled: isOpen('proactive') && heartbeatEnabled,
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
    pagination: 'client',
    selectItems: payload => payload.scheduled_actions,
    selectTotal: payload => payload.total,
    enabled: isOpen('scheduled'),
  });

  // The workboard (ADR-276): tickets that need THIS person — a run stopped on
  // their answer, or something overdue. Flag-gated like every program section.
  const workboard = usePagedSection<{ tickets: TicketRow[]; total: number }, TicketRow>({
    path: '/workboard/needs-me',
    selectItems: payload => payload.tickets,
    selectTotal: payload => payload.total,
    enabled: isOpen('workboard') && Boolean(config?.features?.workboard_enabled),
  });
  const workboardEnabled = Boolean(config?.features?.workboard_enabled);

  // One press re-reads what the page shows. Every OPEN section restarts its
  // query (a folded one has none to restart). The totals, the SMS archive and
  // the discussion openings re-read on the application's resource signal —
  // the one a write elsewhere sends — so one publication refreshes all three
  // without a second read racing it.
  const refreshAll = () => {
    for (const section of [offers, peers, proactive, interests, reminders, scheduled, workboard]) {
      section.refetch();
    }
    if (ownerId) publishApplicationResources(ownerId, SIGNALLED_RESOURCES);
    else void retryCounts();
  };

  return {
    config,
    counts,
    countsError,
    countsLoading,
    retryCounts,
    refreshAll,
    track,
    offers,
    peers,
    proactive,
    interests,
    reminders,
    scheduled,
    workboard,
    workboardEnabled,
  };
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

/** The workboard section (ADR-276), extracted for the same reason as the
 * proposals one: the flag gate and the rows live with the section, so the hub
 * component does not grow a branch per program. */
function WorkboardHubSection({
  enabled,
  section,
  tickets,
  lng,
}: {
  enabled: boolean;
  section: Omit<HubSectionProps, 'icon' | 'children'>;
  tickets: readonly TicketRow[] | undefined;
  lng: string;
}) {
  if (!enabled) return null;
  return (
    <HubSection icon={LayoutGrid} {...section}>
      <NeedsMeList tickets={tickets ?? []} lng={lng as Language} />
    </HubSection>
  );
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
  const summaryRef = useRef<HTMLElement>(null);
  const decisions = useOfferDecisions({
    lng,
    onDecided: restoreFocus => {
      if (restoreFocus) summaryRef.current?.focus();
      offers.refetch();
    },
  });
  if (!enabled) return null;
  return (
    <HubSection icon={Lightbulb} {...section} summaryRef={summaryRef}>
      <OpenOffersList
        offers={(offers.items ?? []).filter(offer => !decisions.decided.has(offer.id))}
        locale={locale}
        decisions={decisions}
      />
    </HubSection>
  );
}

/** Each register owns a heading and a single quiet surface, not nested cards. */
function NotificationRegister({
  id,
  title,
  icon,
  children,
  className,
}: {
  id: string;
  title: string;
  icon: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      aria-labelledby={id}
      className={`min-w-0 rounded-2xl border border-border bg-card p-4 sm:p-5 ${className ?? ''}`}
    >
      <SectionHeader
        id={id}
        title={title}
        icon={icon}
        level={2}
        className="border-b border-border pb-4"
      />
      <div className="divide-y divide-border">{children}</div>
    </section>
  );
}

/** Delivered histories share presentation while retaining their own query gates. */
function DeliveredNotifications({
  sections,
  locale,
}: {
  sections: ReturnType<typeof useHubSections>;
  locale: string;
}) {
  const { t } = useTranslation();
  const { config, counts, track, peers, proactive, interests } = sections;
  const shell = <TItem,>(key: string, section: PagedSection<TItem>, countKey: keyof HubCounts) =>
    sectionShell(key, section, t, track(key), counts?.[countKey] ?? undefined);
  return (
    <>
      {' '}
      {config?.features?.peers_enabled && (
        <HubSection icon={MessageSquare} {...shell('peer_messages', peers, 'peer_messages')}>
          <RelayedMessagesList
            messages={peers.items ?? []}
            locale={locale}
            presentation="timeline"
          />
        </HubSection>
      )}
      {config?.features?.heartbeat_enabled && (
        <HubSection icon={Sparkles} {...shell('proactive', proactive, 'proactive')}>
          <HeartbeatHistory
            notifications={proactive.items}
            total={proactive.total}
            firstLoad={false}
            loading={proactive.loading}
            error={null}
            locale={locale}
            presentation="timeline"
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
          presentation="timeline"
        />
      </HubSection>
    </>
  );
}

export function NotificationsHub({
  lng,
  onOpenJournal,
}: {
  lng: Language;
  onOpenJournal?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = getIntlLocale(i18n.language as Language);
  const sections = useHubSections();
  const { config, counts, track, offers, reminders, scheduled, workboard, workboardEnabled } =
    sections;
  const shell = <TItem,>(key: string, section: PagedSection<TItem>, countKey: keyof HubCounts) =>
    sectionShell(key, section, t, track(key), counts?.[countKey] ?? undefined);

  return (
    <div className="min-w-0 space-y-6">
      <SectionHeader
        title={t('notifications_hub.title')}
        icon={Bell}
        level={1}
        description={t('notifications_hub.subtitle')}
        actions={
          <AlertsViewActions
            onOpenJournal={onOpenJournal}
            lng={lng}
            view="hub"
            switchable={!onOpenJournal && Boolean(config?.features?.activity_timeline_enabled)}
            busy={sections.countsLoading}
            onRefresh={sections.refreshAll}
          />
        }
      />

      {sections.countsError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/5 p-3">
          <p role="alert" className="text-sm text-destructive">
            {t('notifications_hub.counts_error')}
          </p>
          <Button
            size="sm"
            onClick={() => void sections.retryCounts()}
            isLoading={sections.countsLoading}
          >
            {t('common.retry')}
          </Button>
        </div>
      )}

      {config?.features?.heartbeat_enabled && (
        <div className="rounded-2xl border border-primary/20 bg-primary/5 px-4 sm:px-5">
          <ProposalsHubSection
            enabled
            section={shell('offers', offers, 'offers')}
            offers={offers}
            lng={lng}
            locale={locale}
          />
        </div>
      )}

      {/* Future first in linear/mobile reading. Independent registers retain
          the accepted desktop placement: delivered left, upcoming right. */}
      <div className="grid min-w-0 items-start gap-5 lg:grid-cols-2">
        <NotificationRegister
          id="hub-upcoming"
          title={t('notifications_hub.groups.upcoming')}
          icon={CalendarClock}
          className="lg:col-start-2 lg:row-start-1"
        >
          <HubSection icon={Bell} {...shell('reminders', reminders, 'reminders')}>
            <PendingRemindersList reminders={reminders.items ?? []} locale={locale} />
          </HubSection>
          <HubSection icon={CalendarClock} {...shell('scheduled', scheduled, 'scheduled')}>
            <ScheduledActionsList actions={scheduled.items ?? []} locale={locale} />
          </HubSection>
          <WorkboardHubSection
            enabled={workboardEnabled}
            section={shell('workboard', workboard, 'workboard')}
            tickets={workboard.items}
            lng={lng}
          />
        </NotificationRegister>

        <NotificationRegister
          id="hub-received"
          title={t('notifications_hub.groups.received')}
          icon={History}
          className="lg:col-start-1 lg:row-start-1"
        >
          <DeliveredNotifications sections={sections} locale={locale} />
          <DiscussionsHubSection total={counts?.discussions} locale={locale} />
          <SmsHubSection lng={lng} total={counts?.sms} />
        </NotificationRegister>
      </div>
    </div>
  );
}
