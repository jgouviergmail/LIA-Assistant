'use client';

/**
 * What a meeting says about its format and its lineage (ADR-259), kept out of
 * the panels hotspot: the format fact (name, how it was chosen, the model's
 * reason when it chose), and the links between minutes written from the same
 * transcript.
 */

import { GitBranch } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { MeetingDetail } from '@/types/meetings';

type FormatFacts = Pick<
  MeetingDetail,
  'template_name' | 'template_selection' | 'template_selection_reason'
>;

/** The « Format » fact of the header list; nothing when the meeting has no template yet. */
export function MeetingFormatFact({ lng, meeting }: { lng: Language; meeting: FormatFacts }) {
  const { t } = useTranslation(lng);
  if (!meeting.template_name) return null;
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{t('meetings.detail.format')}</dt>
      <dd className="text-sm">
        <span>{meeting.template_name}</span>
        {meeting.template_selection && (
          <>
            <span className="text-muted-foreground"> · </span>
            <span className="text-muted-foreground">
              {t(`meetings.detail.format_selection.${meeting.template_selection}`)}
            </span>
          </>
        )}
      </dd>
      {meeting.template_selection === 'auto' && meeting.template_selection_reason && (
        <dd className="text-xs text-muted-foreground">{meeting.template_selection_reason}</dd>
      )}
    </div>
  );
}

type Lineage = Pick<MeetingDetail, 'source_meeting_id' | 'derived_count'>;

/** The links between minutes sharing one transcript; nothing when there are none. */
export function MeetingLineage({
  lng,
  meeting,
  onOpenMeeting,
}: {
  lng: Language;
  meeting: Lineage;
  onOpenMeeting: (id: string) => void;
}) {
  const { t } = useTranslation(lng);
  const source = meeting.source_meeting_id;
  if (source === null && meeting.derived_count === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
      <GitBranch className="h-4 w-4 text-primary" aria-hidden="true" />
      {source !== null && (
        <Button
          type="button"
          variant="link"
          size="sm"
          className="h-auto p-0"
          onClick={() => onOpenMeeting(source)}
        >
          {t('meetings.detail.derived_from')}
        </Button>
      )}
      {meeting.derived_count > 0 && (
        <span>{t('meetings.detail.derived_count', { count: meeting.derived_count })}</span>
      )}
    </div>
  );
}
