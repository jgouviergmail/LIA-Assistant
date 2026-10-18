'use client';

import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { useAuth } from '@/hooks/useAuth';
import { formatInstant } from '@/lib/format-instant';
import type { CapabilityOrigin } from '@/lib/capability-sharing';

interface Props {
  origin?: CapabilityOrigin | null;
  lng: string;
}

function OriginNote({ origin, lng }: { origin: CapabilityOrigin; lng: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const sender = t('settings.capability_share.origin_by', {
    name: origin.sender_display_name ?? t('settings.capability_share.unknown_sender'),
  });
  const date = t('settings.capability_share.origin_on', {
    date: formatInstant(origin.shared_at, lng, 'medium', user?.timezone),
  });
  return (
    <Badge
      variant="outline"
      role="note"
      aria-label={`${sender} ${date}`}
      className="max-w-full flex-wrap gap-x-1 whitespace-normal break-words border-primary/30 text-primary text-xs"
    >
      <span className="min-w-0 break-words">{sender}</span>
      <time dateTime={origin.shared_at} title={origin.shared_at}>
        {date}
      </time>
    </Badge>
  );
}

export function CapabilityOriginBadge({ origin, lng }: Props) {
  if (!origin || Number.isNaN(Date.parse(origin.shared_at))) return null;
  return <OriginNote origin={origin} lng={lng} />;
}
