'use client';

/**
 * Minutes that do not exist yet on a READY meeting (ADR-259): a row created
 * by « new minutes from this transcript » is READY with no report while the
 * server writes. A failed write leaves the row explainable — the error, a
 * retry on the same template, a delete — rather than an empty page.
 */

import { RefreshCw, Trash2 } from 'lucide-react';

import { MeetingProgress } from '@/components/meetings/MeetingProgress';
import {
  type MeetingActions,
  meetingErrorLabel,
} from '@/components/meetings/useMeetingActions';
import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MeetingDetail } from '@/types/meetings';

export interface MeetingPendingPanelProps {
  lng: Language;
  meeting: Pick<
    MeetingDetail,
    'status' | 'stage' | 'report' | 'last_error_code' | 'template_ref' | 'template_name'
  >;
  actions: MeetingActions;
}

export function MeetingPendingPanel({ lng, meeting, actions }: MeetingPendingPanelProps) {
  const { t } = useTranslation(lng);
  if (meeting.stage !== null) {
    return (
      <section className="rounded-lg border border-primary/30 bg-primary/5 p-4">
        <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold">
          <RefreshCw className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
          {t('meetings.detail.pending_title')}
          {meeting.template_name && (
            <span className="font-normal text-muted-foreground">· {meeting.template_name}</span>
          )}
        </h2>
        <MeetingProgress lng={lng} status={meeting.status} stage={meeting.stage} />
        <p className="mt-2 text-xs text-muted-foreground">{t('meetings.detail.pending_hint')}</p>
      </section>
    );
  }
  const templateRef = meeting.template_ref;
  return (
    <section className="rounded-lg border border-destructive/40 bg-destructive/10 p-4">
      <h2 className="text-sm font-semibold text-destructive">
        {t('meetings.detail.pending_failed_title')}
      </h2>
      {meeting.last_error_code && (
        <p className="mt-1 text-sm">{meetingErrorLabel(t, meeting.last_error_code)}</p>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        {templateRef !== null && (
          <Button
            type="button"
            size="sm"
            onClick={() => void actions.reformat({ template_ref: templateRef, mode: 'replace' })}
          >
            <RefreshCw className="mr-1 h-4 w-4" aria-hidden="true" />
            {t('meetings.detail.try_again')}
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
