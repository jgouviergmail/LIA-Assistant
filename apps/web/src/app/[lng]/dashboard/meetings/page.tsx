'use client';

/**
 * The user's meetings (ADR-258): every recording and where its minutes stand,
 * with row selection and bulk delete (ADR-259).
 *
 * The page owns paging; `MeetingRows` owns the selection and is keyed by the
 * page offset, so a page change resets the selection by construction (no
 * effect resetting state). Rows the server would skip (live, processing) are
 * not selectable, so the announced count is the count that will be deleted.
 */

import { useState } from 'react';
import { ClipboardList, LibraryBig, MessageSquare, Mic } from 'lucide-react';
import { toast } from 'sonner';

import { useMeetingRecorderContext } from '@/components/meetings/MeetingRecorderProvider';
import { MeetingSelectionBar } from '@/components/meetings/MeetingSelectionBar';
import { MeetingStatusBadge } from '@/components/meetings/MeetingStatusBadge';
import { SectionToolbar, type ToolbarAction } from '@/components/settings/SectionToolbar';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeetingList, type UseMeetingListReturn } from '@/hooks/useMeetings';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';
import { formatElapsed } from '@/lib/meetings/format';
import { isSelectable, pageSelectionState, toggleId } from '@/lib/meetings/selection';
import type { MeetingSummary } from '@/types/meetings';

const PAGE_SIZE = 20;

interface MeetingsPageProps {
  params: Promise<{ lng: string }>;
}

function MeetingRow({
  lng,
  meeting,
  selected,
  onToggle,
  onOpen,
}: {
  lng: Language;
  meeting: MeetingSummary;
  selected: boolean;
  onToggle: () => void;
  onOpen: () => void;
}) {
  const { t } = useTranslation(lng);
  const dateFormat = new Intl.DateTimeFormat(lng, { dateStyle: 'medium', timeStyle: 'short' });
  const title = meeting.title ?? t('meetings.list.untitled');
  const selectable = isSelectable(meeting);
  return (
    <li className="flex flex-wrap items-center gap-3 px-2 py-3 sm:px-4">
      {/* 44 px touch target around the native 16 px box: the label is part of
          the target, and its (visually hidden) text is the checkbox's name. */}
      <label
        className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center"
        title={selectable ? undefined : t('meetings.list.not_selectable')}
      >
        <Checkbox
          checked={selected}
          aria-disabled={!selectable}
          onChange={() => selectable && onToggle()}
        />
        <span className="sr-only">{t('meetings.list.select_row', { title })}</span>
      </label>
      <button
        type="button"
        className="min-w-0 flex-1 text-left"
        aria-label={t('meetings.list.open', { title })}
        onClick={onOpen}
      >
        <span className="block truncate font-medium hover:underline">{title}</span>
        <span className="block text-xs text-muted-foreground">
          {dateFormat.format(new Date(meeting.started_at))}
          {meeting.audio_duration_seconds
            ? ` · ${formatElapsed(meeting.audio_duration_seconds)}`
            : ''}
          {meeting.status === 'ready' &&
            ` · ${t('meetings.list.participants', { count: meeting.participants_count })} · ${t(
              'meetings.list.actions',
              { count: meeting.action_items_count }
            )}`}
          {/* What the meeting cost, when anything priced was spent. */}
          {meeting.total_cost_eur !== null &&
            meeting.total_cost_eur > 0 &&
            ` · ${formatEuro(meeting.total_cost_eur, 4, lng)}`}
          {/* The format the minutes were written in (ADR-259). */}
          {meeting.template_name && ` · ${meeting.template_name}`}
        </span>
      </button>
      <MeetingStatusBadge lng={lng} status={meeting.status} stage={meeting.stage} />
    </li>
  );
}

/** The rows of one page with their selection; remounted by the page on every offset change. */
function MeetingRows({
  lng,
  list,
  onDeleted,
}: {
  lng: Language;
  list: UseMeetingListReturn;
  onDeleted: (deletedCount: number) => Promise<void>;
}) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const { confirm, confirmDialog } = useConfirm();
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  const { meetings } = list;

  const selectableIds = meetings.filter(isSelectable).map(m => m.id);
  const chosen = selectableIds.filter(id => selected.has(id));
  const pageState = pageSelectionState(selectableIds, selected);

  const remove = async () => {
    if (chosen.length === 0 || list.isDeleting) return;
    const ok = await confirm({
      title: t('meetings.list.confirm_bulk_delete_title'),
      description: t('meetings.list.confirm_bulk_delete_description', { count: chosen.length }),
      confirmLabel: t('meetings.list.delete_selected', { count: chosen.length }),
      destructive: true,
    });
    if (!ok) return;
    try {
      const result = await list.bulkDelete(chosen);
      if (result === null) return;
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
      {chosen.length > 0 && (
        <MeetingSelectionBar
          lng={lng}
          count={chosen.length}
          pageState={pageState}
          onSelectAll={() => setSelected(new Set(selectableIds))}
          onClear={() => setSelected(new Set())}
          onDelete={() => void remove()}
          deleting={list.isDeleting}
        />
      )}
      <ul className="divide-y divide-border/60 rounded-lg border border-border/60 bg-card/60">
        {meetings.map(meeting => (
          <MeetingRow
            key={meeting.id}
            lng={lng}
            meeting={meeting}
            selected={selected.has(meeting.id)}
            onToggle={() => setSelected(toggleId(selected, meeting.id))}
            onOpen={() => router.push(`/dashboard/meetings/${meeting.id}`)}
          />
        ))}
      </ul>
    </div>
  );
}

/** The list header's actions: record (when the recorder is mounted) and the templates. */
function useToolbarActions(
  t: (key: string) => string,
  router: ReturnType<typeof useLocalizedRouter>
): { primary: ToolbarAction; secondary: ToolbarAction[] } {
  const recorder = useMeetingRecorderContext();
  const templates: ToolbarAction = {
    key: 'templates',
    label: t('meetings.list.templates'),
    icon: LibraryBig,
    onSelect: () => router.push('/dashboard/meetings/templates'),
    pinned: true,
  };
  if (recorder === null) return { primary: templates, secondary: [] };
  const record: ToolbarAction = {
    key: 'record',
    label: t('meetings.list.record'),
    icon: Mic,
    // Stated, not removed, while a recording runs: the banner owns the stop.
    blocked: recorder.isLive,
    onSelect: () => {
      if (!recorder.isLive) void recorder.start();
    },
  };
  return { primary: record, secondary: [templates] };
}

export default function MeetingsPage({ params }: MeetingsPageProps) {
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const toolbar = useToolbarActions(t, router);
  const [offset, setOffset] = useState(0);
  const list = useMeetingList(PAGE_SIZE, offset);
  const { meetings, total, isLoading, isUnavailable } = list;

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
      <header className="space-y-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <ClipboardList className="h-6 w-6 text-primary" aria-hidden="true" />
            {t('meetings.list.title')}
          </h1>
          <p className="text-sm text-muted-foreground">{t('meetings.list.subtitle')}</p>
        </div>
        <SectionToolbar
          count={total > 0 ? t('meetings.list.total', { count: total }) : ''}
          menuLabel={t('common.more_actions')}
          primary={toolbar.primary}
          secondary={toolbar.secondary}
        />
      </header>

      {isLoading ? (
        <div className="space-y-3">
          <LoadingAnnouncement />
          {[1, 2, 3].map(i => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      ) : isUnavailable || meetings.length === 0 ? (
        <EmptyState
          variant="page"
          icon={ClipboardList}
          title={t('meetings.list.empty_title')}
          description={t('meetings.list.empty_description')}
          reason="no-data"
          action={{
            label: t('meetings.list.empty_action'),
            onClick: () => router.push('/dashboard/chat'),
            icon: MessageSquare,
          }}
        />
      ) : (
        <MeetingRows key={offset} lng={lng} list={list} onDeleted={afterDelete} />
      )}

      {total > PAGE_SIZE && (
        <nav className="flex items-center justify-between" aria-label={t('common.pagination')}>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-disabled={offset === 0}
            onClick={() => offset > 0 && setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            {t('common.previous')}
          </Button>
          <Button
            type="button"
            variant="outline"
            size="sm"
            aria-disabled={offset + PAGE_SIZE >= total}
            onClick={() => offset + PAGE_SIZE < total && setOffset(offset + PAGE_SIZE)}
          >
            {t('common.next')}
          </Button>
        </nav>
      )}
    </div>
  );
}
