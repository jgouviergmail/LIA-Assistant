'use client';

/**
 * The user's meetings (ADR-258): every recording and where its minutes stand,
 * with row selection and bulk delete (ADR-259).
 *
 * The page owns paging; `MeetingRows` owns the selection and is keyed by the
 * page offset, so a page change resets the selection by construction (no
 * effect resetting state). Rows the server would skip (live, processing) are
 * not selectable; the server still decides which deletions are allowed.
 */

import { useEffect, useId, useMemo, useRef, useState, type RefObject } from 'react';
import {
  AlertCircle,
  CalendarDays,
  ClipboardList,
  MessageSquare,
  Mic,
  Moon,
  RefreshCw,
  Search,
  Sun,
  Sunrise,
  Upload,
} from 'lucide-react';

import { MeetingNavigationProvider } from './MeetingNavigation';
import { MeetingImportDialog } from '@/components/meetings/MeetingImportDialog';
import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import { BackLink } from '@/components/ui/back-link';
import { MeetingSelectionBar } from '@/components/meetings/MeetingSelectionBar';
import { MeetingTimelineEntry } from '@/components/meetings/MeetingTimelineEntry';
import type { ToolbarAction } from '@/components/settings/SectionToolbar';
import { Button } from '@/components/ui/button';
import { Pagination } from '@/components/ui/pagination';
import { SectionHeader } from '@/components/ui/section-header';
import { TimelineDayGroup, TimelineGroup } from '@/components/ui/timeline-group';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchInput } from '@/components/ui/search-input';
import { useConfirm } from '@/components/ui/use-confirm';
import { useAppConfig } from '@/hooks/useAppConfig';
import { useBackOrigin } from '@/hooks/useBackOrigin';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingList, type UseMeetingListReturn } from '@/hooks/useMeetings';
import { useAuth } from '@/hooks/useAuth';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useApplicationAccountToast } from '@/hooks/useApplicationAccountToast';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { backDestination, withOrigin } from '@/lib/back-origin';
import { useSearchParams } from 'next/navigation';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { meetingListPage, meetingListQuery, meetingListSearch } from '@/lib/meetings/list-location';
import { projectMeetingTimeline, type MeetingPeriod } from '@/lib/meetings/timeline';
import { isSelectable, pageSelectionState, toggleId } from '@/lib/meetings/selection';

const PAGE_SIZE = 20;
const PERIOD_ICONS = {
  night: Moon,
  morning: Sunrise,
  midday: Sun,
  afternoon: Sun,
  evening: Moon,
  unknown: CalendarDays,
} satisfies Record<MeetingPeriod, typeof Sun>;

interface MeetingsWorkspaceProps {
  lng: Language;
  embedded?: boolean;
  active?: boolean;
  onOpenMeeting?: (id: string) => void;
  onEmptyAction?: () => void;
}

/** The rows of one page with their selection; remounted by the page on every offset change. */
function MeetingRows({
  lng,
  list,
  onDeleted,
  page,
  origin,
  query,
}: {
  lng: Language;
  list: UseMeetingListReturn;
  onDeleted: (deletedCount: number) => Promise<void>;
  page: number;
  origin: string | null;
  query: string;
}) {
  const { t } = useTranslation(lng);
  const { confirm, confirmDialog } = useConfirm();
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const toast = useApplicationAccountToast(user?.id);
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const { meetings } = list;
  const timeline = useMemo(() => projectMeetingTimeline(meetings, lng), [meetings, lng]);
  const headingPrefix = useId();
  const confirming = useRef(false);

  const selectableIds = meetings.filter(isSelectable).map(m => m.id);
  const chosen = selectableIds.filter(id => selected.has(id));
  const pageState = pageSelectionState(selectableIds, selected);
  // A refreshed processing row must not keep a hidden selection which could
  // reappear without the reader choosing it when processing finishes.
  if (chosen.length !== selected.size) setSelected(new Set(chosen));

  const remove = async () => {
    if (!isCurrent() || chosen.length === 0 || list.isDeleting || confirming.current) return;
    confirming.current = true;
    const ok = await confirm({
      title: t('meetings.list.confirm_bulk_delete_title'),
      description: t('meetings.list.confirm_bulk_delete_description', { count: chosen.length }),
      confirmLabel: t('meetings.list.delete_selected', { count: chosen.length }),
      destructive: true,
    });
    confirming.current = false;
    if (!ok || !isCurrent()) return;
    try {
      const result = await list.bulkDelete(chosen);
      if (result === null || !isCurrent()) return;
      setSelected(new Set());
      if (result.deleted.length > 0) {
        toast.success(t('meetings.list.bulk_deleted', { count: result.deleted.length }));
      }
      if (result.skipped.length > 0) {
        toast.info(t('meetings.list.bulk_skipped', { count: result.skipped.length }));
      }
      await onDeleted(result.deleted.length);
    } catch {
      toast.error(t('common.error'));
    }
  };

  return (
    <div className="space-y-3">
      {confirmDialog}
      <MeetingSelectionBar
        lng={lng}
        count={chosen.length}
        canSelectAll={selectableIds.length > 0}
        pageState={pageState}
        onSelectAll={() => setSelected(new Set(selectableIds))}
        onClear={() => setSelected(new Set())}
        onDelete={() => void remove()}
        deleting={list.isDeleting}
      />
      {/* Keep the existing row height, including wrapping, without displaying the timezone hint. */}
      <p
        aria-hidden="true"
        className="invisible flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground"
      >
        <CalendarDays className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
        {t('meetings.list.display_timezone', { timezone: timeline.timeZone })}
      </p>
      <div className="space-y-6">
        {timeline.days.map(day => (
          <TimelineDayGroup
            key={day.id}
            headingId={`${headingPrefix}-day-${day.id}`}
            level={2}
            heading={day.label ?? t('meetings.list.unknown_date')}
            dayNumber={day.dayNumber}
            month={day.month}
          >
            {day.periods.map(period => (
              <TimelineGroup
                key={period.id}
                headingId={`${headingPrefix}-day-${day.id}-period-${period.id}`}
                icon={PERIOD_ICONS[period.key]}
                level={3}
                heading={t(`meetings.list.period.${period.key}`)}
                className="space-y-0 [&>div:first-child]:px-4 [&>div:first-child]:pt-4"
              >
                <ul className="divide-y divide-border">
                  {period.entries.map(item => (
                    <MeetingTimelineEntry
                      key={item.meeting.id}
                      item={item}
                      lng={lng}
                      detailHref={buildLocalizedPath(
                        withOrigin(
                          `/dashboard/meetings/${encodeURIComponent(item.meeting.id)}${meetingListSearch(page, query)}`,
                          origin
                        ),
                        lng
                      )}
                      selected={selected.has(item.meeting.id)}
                      onToggle={() => setSelected(toggleId(selected, item.meeting.id))}
                    />
                  ))}
                </ul>
              </TimelineGroup>
            ))}
          </TimelineDayGroup>
        ))}
      </div>
    </div>
  );
}

/**
 * The list header's actions: record (when the recorder is mounted) and import a
 * recording file (when the instance offers it, 2026-10-24).
 */
function useToolbarActions(t: (key: string) => string, onImport: () => void): ToolbarAction[] {
  const recorder = useMeetingRecorderContext();
  const { config } = useAppConfig();
  const actions: ToolbarAction[] = [];
  if (recorder !== null)
    actions.push({
      key: 'record',
      label: t('meetings.list.record'),
      icon: Mic,
      // Stated, not removed, while a recording runs: the banner owns the stop.
      blocked: recorder.isLive,
      onSelect: () => {
        if (!recorder.isLive) void recorder.start();
      },
    });
  if (config?.features?.meetings_import_enabled)
    actions.push({
      key: 'import',
      label: t('meetings.list.import'),
      icon: Upload,
      onSelect: onImport,
    });
  return actions;
}

export function MeetingsWorkspace(props: MeetingsWorkspaceProps) {
  const { user } = useAuth();
  return (
    <MeetingNavigationProvider onOpen={props.onOpenMeeting}>
      <AccountMeetingsPage key={user?.id ?? 'signed-out'} {...props} />
    </MeetingNavigationProvider>
  );
}

function AccountMeetingsPage({
  lng,
  embedded = false,
  active = true,
  onEmptyAction,
}: MeetingsWorkspaceProps) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const origin = useBackOrigin();
  const back = backDestination(origin);
  const searchParams = useSearchParams();
  const [importOpen, setImportOpen] = useState(false);
  const toolbar = useToolbarActions(t, () => setImportOpen(true));
  const [query, setQuery] = useState(() =>
    embedded ? '' : meetingListQuery(searchParams.get('q'))
  );
  const [offset, setOffset] = useState(() =>
    embedded ? 0 : (meetingListPage(searchParams.get('page')) - 1) * PAGE_SIZE
  );
  useEffect(() => {
    if (embedded) return;
    const url = new URL(window.location.href);
    if (offset > 0) url.searchParams.set('page', String(offset / PAGE_SIZE + 1));
    else url.searchParams.delete('page');
    if (query) url.searchParams.set('q', query);
    else url.searchParams.delete('q');
    window.history.replaceState(window.history.state, '', url);
  }, [offset, query, embedded]);
  useEffect(() => {
    if (embedded) return;
    const restore = () => {
      const params = new URLSearchParams(window.location.search);
      setOffset((meetingListPage(params.get('page')) - 1) * PAGE_SIZE);
      setQuery(meetingListQuery(params.get('q')));
    };
    window.addEventListener('popstate', restore);
    return () => window.removeEventListener('popstate', restore);
  }, [embedded]);
  const list = useMeetingList(PAGE_SIZE, offset, active, query);
  const search = (value: string) => {
    const next = meetingListQuery(value);
    if (next === query) return;
    setOffset(0);
    setQuery(next);
  };
  const headingRef = useRef<HTMLHeadingElement>(null);
  const { meetings, total, isLoading, isUnavailable, error } = list;

  // A native invalidation may remove the last row of the last page externally.
  // Adjust in this render before committing an inaccessible empty collection.
  if (!isLoading && !error && !isUnavailable && offset > 0 && offset >= total) {
    setOffset(Math.max(0, Math.ceil(total / PAGE_SIZE) - 1) * PAGE_SIZE);
  }

  // A deletion that empties a page past the first one steps back; otherwise
  // the page re-reads its rows (the offset change triggers the read itself).
  const afterDelete = async (deletedCount: number) => {
    if (deletedCount > 0 && deletedCount >= meetings.length && offset > 0) {
      setOffset(Math.max(0, offset - PAGE_SIZE));
      return;
    }
    await list.refetch();
  };

  return (
    <div className="space-y-6">
      <div className="space-y-3">
        {/* Six doors lead here — the header, the phone menu, a minutes card in
            the chat, a recorder toast, the settings section, a slash command —
            and this list had none back. The door that was used travels in the
            URL as a token; with none, the chat is the way out (owner,
            2026-09-10). */}
        {!embedded && <BackLink label={t(back.labelKey)} onClick={() => router.push(back.href)} />}
        <SectionHeader
          headingRef={headingRef}
          level={1}
          icon={ClipboardList}
          title={t('meetings.list.title')}
          description={t('meetings.list.subtitle')}
          actions={
            toolbar.length ? (
              // One row, Import to the right of Record (owner, 2026-10-25): the
              // header stacks its actions, which put Import under Record.
              <div className="flex w-full gap-2 sm:w-auto">
                {toolbar.map((action, index) => (
                  <Button
                    key={action.key}
                    type="button"
                    // The first action leads; the others follow it in outline.
                    variant={index === 0 ? 'default' : 'outline'}
                    aria-disabled={action.blocked}
                    className="h-auto min-h-11 flex-1 whitespace-normal sm:flex-none"
                    onClick={action.onSelect}
                  >
                    <action.icon aria-hidden="true" />
                    {action.label}
                  </Button>
                ))}
              </div>
            ) : undefined
          }
        />
        <SearchInput
          value={query}
          onSearchChange={search}
          placeholder={t('meetings.list.search_placeholder')}
          aria-label={t('meetings.list.search_placeholder')}
          maxLength={200}
          loading={isLoading && meetings.length > 0}
        />
        {total > 0 && (
          <p aria-live="polite" aria-atomic="true" className="text-sm text-muted-foreground">
            {t('meetings.list.total', { count: total })}
          </p>
        )}
      </div>

      <ListLoadError
        lng={lng}
        retry={list.refetch}
        hasError={!!error && !isUnavailable}
        focusTarget={headingRef}
      />
      <div aria-busy={isLoading}>
        <MeetingListContent
          lng={lng}
          list={list}
          onDeleted={afterDelete}
          page={offset / PAGE_SIZE + 1}
          origin={origin}
          query={query}
          onEmptyAction={() =>
            query ? search('') : onEmptyAction ? onEmptyAction() : router.push('/dashboard/chat')
          }
        />
      </div>

      <Pagination
        currentPage={Math.floor(offset / PAGE_SIZE) + 1}
        totalPages={Math.ceil(total / PAGE_SIZE)}
        totalItems={total}
        variant="centered"
        onPageChange={page => setOffset((page - 1) * PAGE_SIZE)}
      />
      <MeetingImportDialog lng={lng} open={importOpen} onOpenChange={setImportOpen} />
    </div>
  );
}

/** Loading, failed, empty and populated are distinct presentation states. */
function MeetingListContent(props: {
  lng: Language;
  list: UseMeetingListReturn;
  onDeleted: (count: number) => Promise<void>;
  page: number;
  origin: string | null;
  query: string;
  onEmptyAction: () => void;
}) {
  const { list } = props;
  if (list.isLoading && list.meetings.length === 0)
    return (
      <div className="space-y-3">
        <LoadingAnnouncement />
        {[1, 2, 3].map(i => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  if (!list.isUnavailable && list.error && list.meetings.length === 0) return null;
  if (list.isUnavailable || list.meetings.length === 0)
    return (
      <MeetingListEmpty
        lng={props.lng}
        filtered={!!props.query && !list.isUnavailable}
        onAction={props.onEmptyAction}
      />
    );
  return <MeetingRows key={JSON.stringify([props.page, props.query])} {...props} />;
}

function MeetingListEmpty({
  lng,
  filtered,
  onAction,
}: {
  lng: Language;
  filtered: boolean;
  onAction: () => void;
}) {
  const { t } = useTranslation(lng);
  return (
    <EmptyState
      variant="page"
      icon={filtered ? Search : ClipboardList}
      title={t(filtered ? 'meetings.list.no_results_title' : 'meetings.list.empty_title')}
      description={t(
        filtered ? 'meetings.list.no_results_description' : 'meetings.list.empty_description'
      )}
      reason={filtered ? 'no-match' : 'no-data'}
      action={{
        label: t(filtered ? 'meetings.list.clear_search' : 'meetings.list.empty_action'),
        onClick: onAction,
        icon: filtered ? Search : MessageSquare,
      }}
    />
  );
}

/** Retry retains stale rows and focus; the hook remains the sole request/owner authority. */
function ListLoadError({
  lng,
  retry,
  hasError,
  focusTarget,
}: {
  lng: Language;
  retry: () => Promise<void>;
  hasError: boolean;
  focusTarget: RefObject<HTMLHeadingElement | null>;
}) {
  const { t } = useTranslation(lng);
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const retryRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  useEffect(() => {
    if (hasError || !restoreFocus.current) return;
    // Removing the recovered error must not strand keyboard focus on body.
    // A manual blur cancels restoration, so a reader who moved on keeps focus.
    if (document.activeElement === document.body) focusTarget.current?.focus();
    restoreFocus.current = false;
  }, [hasError, focusTarget]);
  const run = async () => {
    if (pending.current || !isCurrent()) return;
    restoreFocus.current = document.activeElement === retryRef.current;
    pending.current = true;
    setBusy(true);
    try {
      await retry();
    } finally {
      pending.current = false;
      if (isCurrent()) setBusy(false);
    }
  };
  if (!hasError) return null;
  return (
    <div className="space-y-3 rounded-xl border border-destructive/25 bg-destructive/5 p-4">
      <p role="alert" className="flex items-start gap-2 text-sm">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" aria-hidden="true" />
        {t('meetings.list.load_error')}
      </p>
      <Button
        type="button"
        variant="secondary"
        ref={retryRef}
        onBlur={() => {
          restoreFocus.current = false;
        }}
        aria-disabled={busy}
        aria-busy={busy}
        onClick={() => void run()}
      >
        <RefreshCw
          className={busy ? 'animate-spin motion-reduce:animate-none' : ''}
          aria-hidden="true"
        />
        {t('common.retry')}
      </Button>
    </div>
  );
}
