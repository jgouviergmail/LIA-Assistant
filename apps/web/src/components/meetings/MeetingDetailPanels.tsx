'use client';

/**
 * The panels of the meeting page (ADR-258): facts, progress, failure,
 * minutes with their toolbar, transcript. Each one small (CC discipline);
 * the page composes them and owns the draft.
 */

import {
  ClipboardList,
  Download,
  FileText,
  Mail,
  Pencil,
  RefreshCw,
  RotateCcw,
  Save,
  Trash2,
  X,
} from 'lucide-react';

import { MeetingProgress } from '@/components/meetings/MeetingProgress';
import { MeetingReportEditor } from '@/components/meetings/MeetingReportEditor';
import { MeetingReportView } from '@/components/meetings/MeetingReportView';
import { MeetingStatusBadge } from '@/components/meetings/MeetingStatusBadge';
import { Badge } from '@/components/ui/badge';
import type { MeetingActions } from '@/components/meetings/useMeetingActions';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { apiEndpointUrl } from '@/lib/api-client';
import { formatEuro } from '@/lib/format';
import { meetingPdfEndpoint } from '@/lib/meetings/api';
import { formatElapsed } from '@/lib/meetings/format';
import { costLabel } from '@/components/meetings/MeetingMinutesCard';
import type { MeetingDetail, MeetingReport, TranscriptTurn } from '@/types/meetings';

function Fact({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-sm">{value}</dd>
    </div>
  );
}

function timeRange(lng: Language, meeting: MeetingDetail): string {
  const time = new Intl.DateTimeFormat(lng, {
    timeStyle: 'short',
    timeZone: meeting.client_timezone,
  });
  const start = time.format(new Date(meeting.started_at));
  return meeting.stopped_at ? `${start} – ${time.format(new Date(meeting.stopped_at))}` : start;
}

export function MeetingFacts({ lng, meeting }: { lng: Language; meeting: MeetingDetail }) {
  const { t } = useTranslation(lng);
  const date = new Intl.DateTimeFormat(lng, {
    dateStyle: 'full',
    timeZone: meeting.client_timezone,
  }).format(new Date(meeting.started_at));
  // The two paid units and their sum; a side with no administered price reads
  // « not priced » rather than zero (ADR-185: exact or absent).
  const unknown = t('meetings.detail.cost_unknown');
  const costValue =
    meeting.total_cost_eur === null
      ? null
      : t('meetings.detail.cost_breakdown', {
          total: formatEuro(meeting.total_cost_eur, 4, lng),
          stt: costLabel(meeting.stt_cost_eur, lng, unknown),
          minutes: costLabel(meeting.synthesis_cost_eur, lng, unknown),
        });
  return (
    <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <Fact label={t('meetings.detail.date')} value={date} />
      <Fact label={t('meetings.detail.time')} value={timeRange(lng, meeting)} />
      <Fact
        label={t('meetings.detail.duration')}
        value={
          meeting.audio_duration_seconds ? formatElapsed(meeting.audio_duration_seconds) : null
        }
      />
      <Fact label={t('meetings.detail.location')} value={meeting.location_label} />
      <Fact
        label={t('meetings.detail.engine')}
        value={meeting.stt_provider ? t(`meetings.banner.engine.${meeting.stt_provider}`) : null}
      />
      <Fact label={t('meetings.detail.cost')} value={costValue} />
    </dl>
  );
}

export function ProcessingPanel({ lng, meeting }: { lng: Language; meeting: MeetingDetail }) {
  const { t } = useTranslation(lng);
  return (
    <section className="rounded-lg border border-primary/30 bg-primary/5 p-4">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <RefreshCw className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
        {t('meetings.detail.progress_title')}
      </h2>
      <MeetingProgress lng={lng} status={meeting.status} stage={meeting.stage} />
      <p className="mt-2 text-xs text-muted-foreground">{t('meetings.detail.processing_hint')}</p>
    </section>
  );
}

export function FailedPanel({
  lng,
  meeting,
  actions,
}: {
  lng: Language;
  meeting: MeetingDetail;
  actions: MeetingActions;
}) {
  const { t } = useTranslation(lng);
  return (
    <section className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
      <h2 className="text-sm font-semibold text-destructive">
        {t('meetings.detail.failed_title')}
      </h2>
      {meeting.last_error_code && (
        <p className="mt-1 text-sm">
          {t(`meetings.errors.${meeting.last_error_code}`, {
            defaultValue: t('meetings.errors.unknown', { code: meeting.last_error_code }),
          })}
        </p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {meeting.audio_purged_at === null && (
          <Button type="button" size="sm" onClick={() => void actions.retry()}>
            <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.detail.retry')}
          </Button>
        )}
        <Button type="button" size="sm" variant="destructive" onClick={() => void actions.remove()}>
          <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.delete')}
        </Button>
      </div>
    </section>
  );
}

interface MinutesPanelProps {
  lng: Language;
  meeting: MeetingDetail;
  report: MeetingReport;
  draft: MeetingReport | null;
  regenerating: boolean;
  isActing: boolean;
  onDraftChange: (draft: MeetingReport | null) => void;
  actions: MeetingActions;
}

function MinutesToolbar({
  lng,
  meeting,
  report,
  draft,
  regenerating,
  isActing,
  onDraftChange,
  actions,
}: MinutesPanelProps) {
  const { t } = useTranslation(lng);
  if (draft !== null) {
    return (
      <>
        <Button
          type="button"
          size="sm"
          onClick={() => void actions.save(draft)}
          isLoading={isActing}
        >
          <Save className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('common.save')}
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={() => onDraftChange(null)}>
          <X className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('common.cancel')}
        </Button>
      </>
    );
  }
  const canRebuild = !isActing && !regenerating && meeting.has_transcript;
  return (
    <>
      <Button
        type="button"
        size="sm"
        variant="default"
        aria-disabled={regenerating}
        onClick={() => !regenerating && onDraftChange(structuredClone(report))}
      >
        <Pencil className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.detail.edit')}
      </Button>
      <Button type="button" size="sm" variant="outline" asChild>
        <a href={apiEndpointUrl(meetingPdfEndpoint(meeting.id))} target="_blank" rel="noopener">
          <Download className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.pdf')}
        </a>
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() => !isActing && void actions.email()}
        aria-disabled={isActing}
      >
        <Mail className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.detail.email')}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="outline"
        aria-disabled={!canRebuild}
        onClick={() => canRebuild && void actions.regenerate()}
      >
        <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
        {t('meetings.detail.regenerate')}
      </Button>
      {meeting.report_is_edited && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => void actions.resetReport()}
        >
          <RotateCcw className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.reset')}
        </Button>
      )}
    </>
  );
}

export function MinutesPanel(props: MinutesPanelProps) {
  const { lng, meeting, report, draft, onDraftChange } = props;
  const { t } = useTranslation(lng);
  return (
    <section className="space-y-4 rounded-lg border border-border/60 bg-card/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <FileText className="h-4 w-4 text-primary" aria-hidden="true" />
          {t('meetings.detail.minutes_title')}
        </h2>
        <span className="ml-auto flex flex-wrap gap-2">
          <MinutesToolbar {...props} />
        </span>
      </div>
      {meeting.email_sent_at && (
        <p className="text-xs text-muted-foreground">
          {t('meetings.detail.email_sent', {
            when: new Intl.DateTimeFormat(lng, { dateStyle: 'medium', timeStyle: 'short' }).format(
              new Date(meeting.email_sent_at)
            ),
          })}
        </p>
      )}
      {meeting.index_state && (
        <p className="text-xs text-muted-foreground">
          {t(`meetings.detail.index_${meeting.index_state}`)}
        </p>
      )}
      {draft !== null ? (
        <MeetingReportEditor lng={lng} value={draft} onChange={onDraftChange} />
      ) : (
        <MeetingReportView lng={lng} report={report} />
      )}
    </section>
  );
}

function TranscriptList({ lng, turns }: { lng: Language; turns: TranscriptTurn[] }) {
  const { t } = useTranslation(lng);
  return (
    <ol className="max-h-96 space-y-2 overflow-y-auto rounded-md border border-border/60 p-3 text-sm">
      {turns.map((turn, index) => (
        <li key={`${turn.start}-${index}`} className="grid grid-cols-[3.5rem_4rem_1fr] gap-2">
          <span className="tabular-nums text-muted-foreground">{formatElapsed(turn.start)}</span>
          <span className="font-medium">{turn.speaker}</span>
          <span>{turn.text}</span>
        </li>
      ))}
      {turns.length === 0 && (
        <li className="text-muted-foreground">{t('meetings.detail.transcript_deleted')}</li>
      )}
    </ol>
  );
}

export function TranscriptPanel({
  lng,
  meeting,
  shown,
  onToggle,
  actions,
}: {
  lng: Language;
  meeting: MeetingDetail;
  shown: boolean;
  onToggle: () => void;
  actions: MeetingActions;
}) {
  const { t } = useTranslation(lng);
  return (
    <section className="space-y-3 rounded-lg border border-border/60 bg-card/60 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-base font-semibold">{t('meetings.detail.transcript_title')}</h2>
        {meeting.has_transcript && (
          <span className="ml-auto flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="outline" onClick={onToggle}>
              {t(shown ? 'meetings.detail.transcript_hide' : 'meetings.detail.transcript_show')}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="text-destructive"
              onClick={() => void actions.deleteTranscript()}
            >
              <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
              {t('meetings.detail.delete_transcript')}
            </Button>
          </span>
        )}
      </div>
      {!meeting.has_transcript && (
        <p className="text-sm text-muted-foreground">{t('meetings.detail.transcript_deleted')}</p>
      )}
      {shown && meeting.transcript && <TranscriptList lng={lng} turns={meeting.transcript} />}
    </section>
  );
}

/** Every speaker unnamed → the minutes carry the numbering notice. */
function speakersUnnamed(report: MeetingReport | null): boolean {
  return (
    report !== null &&
    report.participants.length > 0 &&
    report.participants.every(participant => participant.name === null)
  );
}

export function MeetingHeader({
  lng,
  meeting,
  report,
}: {
  lng: Language;
  meeting: MeetingDetail;
  report: MeetingReport | null;
}) {
  const { t } = useTranslation(lng);
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <ClipboardList className="h-6 w-6 text-primary" aria-hidden="true" />
          {report?.title ?? t('meetings.list.untitled')}
        </h1>
        <MeetingStatusBadge
          lng={lng}
          status={meeting.status}
          stage={meeting.stage}
          size="default"
        />
        {report && (
          <Badge variant={meeting.report_is_edited ? 'default' : 'secondary'} size="sm">
            {t(
              meeting.report_is_edited
                ? 'meetings.detail.edited_badge'
                : 'meetings.detail.generated_badge'
            )}
          </Badge>
        )}
      </div>
      <MeetingFacts lng={lng} meeting={meeting} />
      {meeting.audio_gaps > 0 && (
        <p className="text-sm text-warning">
          {t('meetings.detail.gaps_notice', { count: meeting.audio_gaps })}
        </p>
      )}
      {speakersUnnamed(report) && (
        <p className="text-sm text-muted-foreground">{t('meetings.detail.no_names_notice')}</p>
      )}
    </header>
  );
}

/** What a READY meeting shows under its minutes: the transcript and the delete. */
export function ReadyTail({
  lng,
  meeting,
  shown,
  onToggle,
  actions,
}: {
  lng: Language;
  meeting: MeetingDetail;
  shown: boolean;
  onToggle: () => void;
  actions: MeetingActions;
}) {
  const { t } = useTranslation(lng);
  return (
    <>
      <TranscriptPanel
        lng={lng}
        meeting={meeting}
        shown={shown}
        onToggle={onToggle}
        actions={actions}
      />
      <div className="flex justify-end">
        <Button type="button" size="sm" variant="destructive" onClick={() => void actions.remove()}>
          <Trash2 className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.delete')}
        </Button>
      </div>
    </>
  );
}
