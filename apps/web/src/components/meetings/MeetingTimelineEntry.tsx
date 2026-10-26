'use client';

import { MeetingOpenLink } from './MeetingNavigation';
import {
  AudioLines,
  BookOpen,
  CheckCheck,
  Clock3,
  Coins,
  FileText,
  Info,
  Users,
  type LucideIcon,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Disclosure } from '@/components/ui/disclosure';
import { MeetingStatusBadge } from './MeetingStatusBadge';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { formatEuro } from '@/lib/format';
import { formatElapsed } from '@/lib/meetings/format';
import { isSelectable } from '@/lib/meetings/selection';
import type { MeetingTimelineItem } from '@/lib/meetings/timeline';
import type { MeetingSummary } from '@/types/meetings';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';

interface FactProps {
  icon: LucideIcon;
  label: string;
  children: ReactNode;
  wide?: boolean;
}
function Fact({ icon: Icon, label, children, wide }: FactProps) {
  return (
    <div className={wide ? 'basis-full' : ''}>
      <dt className="sr-only">{label}</dt>
      <dd className="flex min-w-0 items-start gap-1.5">
        <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 [overflow-wrap:anywhere]">{children}</span>
      </dd>
    </div>
  );
}

/** Data only: the desktop and folded mobile views share this renderer, never another fetch. */
function RecordingFacts({ meeting, lng }: { meeting: MeetingSummary; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <dl className="flex min-w-0 flex-wrap gap-x-4 gap-y-2 text-xs leading-relaxed text-muted-foreground">
      {meeting.audio_duration_seconds !== null &&
        Number.isFinite(meeting.audio_duration_seconds) && (
          <Fact icon={Clock3} label={t('meetings.detail.duration')}>
            {formatElapsed(meeting.audio_duration_seconds)}
          </Fact>
        )}
      {meeting.status === 'ready' && (
        <>
          <Fact
            icon={Users}
            label={t('meetings.list.participants', { count: meeting.participants_count })}
          >
            {t('meetings.list.participants', { count: meeting.participants_count })}
          </Fact>
          <Fact
            icon={CheckCheck}
            label={t('meetings.list.actions', { count: meeting.action_items_count })}
          >
            {t('meetings.list.actions', { count: meeting.action_items_count })}
          </Fact>
        </>
      )}
      {meeting.total_cost_eur !== null && meeting.total_cost_eur > 0 && (
        <Fact icon={Coins} label={t('meetings.detail.cost')}>
          {formatEuro(meeting.total_cost_eur, 4, lng)}
        </Fact>
      )}
      {meeting.template_name && (
        <Fact icon={FileText} label={t('meetings.detail.format')} wide>
          {meeting.template_name}
          {meeting.template_selection && (
            <span> · {t(`meetings.detail.format_selection.${meeting.template_selection}`)}</span>
          )}
        </Fact>
      )}
      {meeting.index_state && (
        <Fact icon={BookOpen} label={t('meetings.list.index_label')} wide>
          {t(`meetings.detail.index_${meeting.index_state}`)}
        </Fact>
      )}
      {meeting.stt_provider && (
        <Fact icon={AudioLines} label={t('meetings.detail.engine')}>
          {t(`meetings.banner.engine.${meeting.stt_provider}`)}
        </Fact>
      )}
      {meeting.source_meeting_id && (
        <Fact icon={FileText} label={t('meetings.detail.derived_from')} wide>
          <MeetingOpenLink
            id={meeting.source_meeting_id}
            href={buildLocalizedPath(
              `/dashboard/meetings/${encodeURIComponent(meeting.source_meeting_id)}`,
              lng
            )}
            className="text-primary underline underline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
          >
            {t('meetings.detail.derived_from')}
          </MeetingOpenLink>
        </Fact>
      )}
    </dl>
  );
}

function CaptureTimes({ item, lng }: { item: MeetingTimelineItem; lng: Language }) {
  const { t } = useTranslation(lng);
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1 text-sm tabular-nums md:flex-col md:items-start">
      <span className="inline-flex items-center gap-1.5 font-semibold">
        <Clock3 className="h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        {item.start ? (
          <time
            dateTime={item.meeting.started_at}
            aria-label={t('meetings.list.start_time', { time: item.start })}
          >
            {item.start}
          </time>
        ) : (
          <span>{t('meetings.list.unknown_time')}</span>
        )}
      </span>
      {item.end && (
        <span className="inline-flex min-w-0 items-center gap-1.5 text-sm font-semibold text-muted-foreground md:pl-[22px]">
          <span className="md:hidden" aria-hidden="true">
            —
          </span>
          <time
            dateTime={item.meeting.stopped_at ?? undefined}
            aria-label={t('meetings.list.end_time', {
              time: `${item.end}${item.endDay ? ` · ${item.endDay}` : ''}`,
            })}
          >
            {item.end}
            {item.endDay && <span className="ml-1">· {item.endDay}</span>}
          </time>
        </span>
      )}
    </div>
  );
}

export function MeetingTimelineEntry({
  item,
  lng,
  selected,
  onToggle,
  detailHref,
}: {
  item: MeetingTimelineItem;
  lng: Language;
  selected: boolean;
  onToggle: () => void;
  /** Optional localized return-context URL, supplied by a paged list. */
  detailHref?: string;
}) {
  const { t } = useTranslation(lng);
  const { meeting } = item;
  const title = meeting.title?.trim() || t('meetings.list.untitled');
  const selectable = isSelectable(meeting);
  return (
    <li className="min-w-0 px-3 py-4 sm:px-4 md:grid md:grid-cols-[8rem_minmax(0,1fr)] md:gap-4">
      <div className="mb-2 flex min-w-0 flex-wrap items-start justify-between gap-2 md:mb-0 md:block md:pt-3">
        <CaptureTimes item={item} lng={lng} />
        <span className="max-w-full md:hidden [&>span]:h-auto [&>span]:min-h-5 [&>span]:whitespace-normal [&>span]:py-0.5">
          <MeetingStatusBadge lng={lng} status={meeting.status} stage={meeting.stage} />
        </span>
      </div>
      <div className="min-w-0">
        <div className="flex min-w-0 items-start gap-2">
          <label
            className="flex h-[calc(1lh+1.25rem)] min-h-11 w-11 shrink-0 cursor-pointer items-center justify-center leading-relaxed"
            title={selectable ? undefined : t('meetings.list.not_selectable')}
          >
            <Checkbox
              checked={selected}
              aria-disabled={!selectable}
              onChange={() => selectable && onToggle()}
            />
            <span className="sr-only">{t('meetings.list.select_row', { title })}</span>
          </label>
          <MeetingOpenLink
            id={meeting.id}
            href={
              detailHref ??
              buildLocalizedPath(`/dashboard/meetings/${encodeURIComponent(meeting.id)}`, lng)
            }
            className="min-w-0 flex-1 py-2.5 font-medium leading-relaxed text-primary underline-offset-4 [overflow-wrap:anywhere] hover:underline focus-visible:rounded focus-visible:outline-2 focus-visible:outline-ring"
          >
            {title}
          </MeetingOpenLink>
          <span className="hidden max-w-[40%] pt-3 md:block [&>span]:h-auto [&>span]:min-h-5 [&>span]:whitespace-normal [&>span]:py-0.5">
            <MeetingStatusBadge lng={lng} status={meeting.status} stage={meeting.stage} />
          </span>
        </div>
        <div className="hidden pl-[52px] md:block">
          <RecordingFacts meeting={meeting} lng={lng} />
        </div>
        <Disclosure
          surface="nested"
          icon={Info}
          title={t('common.details')}
          className="mt-2 rounded-none border-x-0 border-b-0 px-0 md:hidden [&>summary]:ml-auto [&>summary]:min-h-11 [&>summary]:w-fit [&>summary]:text-sm [&>summary]:font-semibold [&>summary]:text-muted-foreground"
        >
          <RecordingFacts meeting={meeting} lng={lng} />
        </Disclosure>
      </div>
    </li>
  );
}
