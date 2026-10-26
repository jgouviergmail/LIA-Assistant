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

import { useState } from 'react';
import type { Language } from '@/i18n/settings';
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
import { useBackOrigin } from '@/hooks/useBackOrigin';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import { useMeeting } from '@/hooks/useMeetings';
import { useAuth } from '@/hooks/useAuth';
import { useTranslation } from '@/i18n/client';
import { withOrigin } from '@/lib/back-origin';
import { useSearchParams } from 'next/navigation';
import { meetingListPage, meetingListQuery, meetingListSearch } from '@/lib/meetings/list-location';
import type { MeetingDetail, MeetingReport } from '@/types/meetings';

interface MeetingDetailWorkspaceProps {
  lng: Language;
  id: string;
  onBack?: () => void;
  onOpenMeeting?: (id: string) => void;
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

export function MeetingDetailWorkspace(props: MeetingDetailWorkspaceProps) {
  const { user } = useAuth();
  return <AccountMeetingPage key={`${user?.id ?? 'signed-out'}:${props.id}`} {...props} />;
}

function AccountMeetingPage({ lng, id, onBack, onOpenMeeting }: MeetingDetailWorkspaceProps) {
  const { t } = useTranslation(lng);
  const router = useLocalizedRouter();
  // The door that opened the LIST opened this page too: carrying the token
  // back means one hop returns to the screen the reader actually came from,
  // not to a list they never chose to visit.
  const origin = useBackOrigin();
  const searchParams = useSearchParams();
  const page = meetingListPage(searchParams.get('page'));
  const query = meetingListQuery(searchParams.get('q'));
  const listHref = withOrigin(`/dashboard/meetings${meetingListSearch(page, query)}`, origin);
  const navigateBack = () => {
    if (onBack) onBack();
    else router.push(listHref);
  };
  const openMeeting = (target: string) => {
    if (onOpenMeeting) onOpenMeeting(target);
    else router.push(`/dashboard/meetings/${target}`);
  };
  const { confirm, confirmDialog } = useConfirm();
  const [showTranscript, setShowTranscript] = useState(false);
  const [draft, setDraft] = useState<MeetingReport | null>(null);
  const [formatOpen, setFormatOpen] = useState(false);
  const state = useMeeting(id, showTranscript);
  const actions = useMeetingActions(state, {
    t,
    confirm,
    navigateToList: () => navigateBack(),
    navigateToMeeting: openMeeting,
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
          onClick: () => navigateBack(),
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
        <Button type="button" variant="ghost" size="sm" onClick={() => navigateBack()}>
          <ArrowLeft className="mr-1 h-4 w-4" aria-hidden="true" />
          {t('meetings.detail.back')}
        </Button>
      </div>

      <MeetingHeader lng={lng} meeting={meeting} report={report} />
      <MeetingLineage lng={lng} meeting={meeting} onOpenMeeting={openMeeting} />

      {inFlight(meeting) && <ProcessingPanel lng={lng} meeting={meeting} actions={actions} />}
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
