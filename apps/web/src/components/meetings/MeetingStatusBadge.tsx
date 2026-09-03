'use client';

/**
 * One badge for a meeting's status, tone from the shared table (ADR-205/206).
 */

import { Badge } from '@/components/ui/badge';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { meetingStatusTone } from '@/lib/meetings/format';
import type { MeetingStage, MeetingStatus } from '@/types/meetings';

interface MeetingStatusBadgeProps {
  lng: Language;
  status: MeetingStatus;
  /** Shown instead of the status while the server works (`processing`, regeneration). */
  stage?: MeetingStage | null;
  size?: 'sm' | 'default';
}

export function MeetingStatusBadge({ lng, status, stage, size = 'sm' }: MeetingStatusBadgeProps) {
  const { t } = useTranslation(lng);
  const label = stage ? t(`meetings.stage.${stage}`) : t(`meetings.status.${status}`);
  return (
    <Badge variant={meetingStatusTone(status)} size={size}>
      {label}
    </Badge>
  );
}
