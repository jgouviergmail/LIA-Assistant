'use client';

/**
 * One meeting (ADR-258): its facts, its progression while the server works,
 * its minutes to read and edit, and every action on them.
 *
 * Progress is polled (`useMeeting` stops by itself once the row is terminal).
 * Editing is local until saved; « Restore the generated version » goes back to
 * the model's output; « Rebuild with the same format » re-runs the synthesis on
 * the stored transcript and « Change the format » does so with another template,
 * in place or as new minutes (ADR-259). The PDF is a browser navigation (the
 * cookie rides along). The page composes the panels of `MeetingDetailPanels`
 * and owns the draft and the dialog state.
 */

import { use, useState } from 'react';
import { ArrowLeft, ClipboardList } from 'lucide-react';

import { MeetingLineage } from '@/components/meetings/MeetingDetailLinks';
import {
  FailedPanel,
  MeetingHeader,
  MinutesPanel,
  ProcessingPanel,
  ReadyTail,
} from '@/components/meetings/MeetingDetailPanels';
import { MeetingPendingPanel } from '@/components/meetings/MeetingPendingPanel';
import { ReformatDialog } from '@/components/meetings/ReformatDialog';
import { useMeetingActions } from '@/components/meetings/useMeetingActions';
import { Button } from '@/components/ui/button';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import { useLanguageParam } from '@/hooks/useLanguageParam';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeeting } from '@/hooks/useMeetings';
import { useTranslation } from '@/i18n/client';
import type { MeetingDetail, MeetingReport } from '@/types/meetings';

interface MeetingPageProps {
  params: Promise<{ lng: string; id: string }>;
}

function inFlight(meeting: MeetingDetail): boolean {
  return meeting.status === 'stopped' || meeting.status === 'processing';
}

function PageSkeleton() {
  return (
    <div className="space-y-6">
      <LoadingAnnouncement />
      <Skeleton className="h-9 w-72" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-64 w-full" />
    </div>
  );
}

export default function MeetingPage({ params }: MeetingPageProps) {
  const { id } = use(params);
  const lng = useLanguageParam(params);
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  const { confirm, confirmDialog } = useConfirm();
  const [showTranscript, setShowTranscript] = useState(false);
  const [draft, setDraft] = useState<MeetingReport | null>(null);
  const [formatOpen, setFormatOpen] = useState(false);
  const state = useMeeting(id, showTranscript);
  const actions = useMeetingActions(state, {
    t,
    confirm,
    navigateToList: () => router.push('/dashboard/meetings'),
    navigateToMeeting: target => router.push(`/dashboard/meetings/${target}`),
    setDraft,
    setShowTranscript,
  });
  const { meeting, isLoading, isNotFound, isActing } = state;

  if (isLoading) return <PageSkeleton />;

  if (isNotFound || meeting === null) {
    return (
      <EmptyState
        variant="page"
        icon={ClipboardList}
        title={t('meetings.detail.not_found')}
        reason="no-data"
        action={{
          label: t('meetings.detail.back'),
          onClick: () => router.push('/dashboard/meetings'),
          icon: ArrowLeft,
        }}
      />
    );
  }

  const report = meeting.report;
  const regenerating = meeting.status === 'ready' && meeting.stage !== null;

  return (
    <div className="space-y-6" aria-busy={isActing || regenerating}>
      {confirmDialog}
      <div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => router.push('/dashboard/meetings')}
        >
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.back')}
        </Button>
      </div>

      <MeetingHeader lng={lng} meeting={meeting} report={report} />
      <MeetingLineage
        lng={lng}
        meeting={meeting}
        onOpenMeeting={target => router.push(`/dashboard/meetings/${target}`)}
      />

      {inFlight(meeting) && <ProcessingPanel lng={lng} meeting={meeting} />}
      {meeting.status === 'failed' && <FailedPanel lng={lng} meeting={meeting} actions={actions} />}
      {meeting.status === 'ready' && report === null && (
        <MeetingPendingPanel lng={lng} meeting={meeting} actions={actions} />
      )}

      {report && (
        <MinutesPanel
          lng={lng}
          meeting={meeting}
          report={report}
          draft={draft}
          regenerating={regenerating}
          isActing={isActing}
          onDraftChange={setDraft}
          actions={actions}
          onChangeFormat={() => setFormatOpen(true)}
        />
      )}
      {meeting.status === 'ready' && (
        <ReformatDialog
          lng={lng}
          open={formatOpen}
          onOpenChange={setFormatOpen}
          meeting={meeting}
          isActing={isActing}
          onSubmit={request => {
            setFormatOpen(false);
            void actions.reformat(request);
          }}
        />
      )}

      {meeting.status === 'ready' && (
        <ReadyTail
          lng={lng}
          meeting={meeting}
          shown={showTranscript}
          onToggle={() => setShowTranscript(v => !v)}
          actions={actions}
        />
      )}
    </div>
  );
}
