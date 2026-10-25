'use client';

import { useTranslation } from 'react-i18next';
import { Send } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Disclosure } from '@/components/ui/disclosure';
import { useAuth } from '@/hooks/useAuth';
import { formatInstant } from '@/lib/format-instant';
import type { CapabilityOrigin, CapabilityShare } from '@/lib/capability-sharing';
import { CapabilityOriginBadge } from './CapabilityOriginBadge';

interface Props {
  origin?: CapabilityOrigin | null;
  sharedWith?: readonly CapabilityShare[];
  lng: string;
}

/**
 * Where a capability came from and whom it went to, under the card's rule
 * (owner request 2026-10-24). A received copy names its sender; an item the
 * owner shared folds its recipients, one line each. Each side sees its own
 * act only — never the state of the other side's copy.
 */
export function CapabilityProvenance({ origin, sharedWith = [], lng }: Props) {
  if (!origin && sharedWith.length === 0) return null;
  return (
    <div className="min-w-0 space-y-2">
      <CapabilityOriginBadge origin={origin} lng={lng} />
      {sharedWith.length > 0 && <SharedWith shares={sharedWith} lng={lng} />}
    </div>
  );
}

function SharedWith({ shares, lng }: { shares: readonly CapabilityShare[]; lng: string }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  return (
    <Disclosure
      icon={Send}
      title={t('settings.capability_share.shared_with_title')}
      badge={shares.length}
    >
      <ul className="space-y-1.5 text-xs">
        {shares.map(share => (
          <li key={share.transfer_id} className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            <span className="min-w-0 break-words font-medium">
              {share.recipient_display_name ?? t('settings.capability_share.unknown_recipient')}
            </span>
            <span aria-hidden="true">·</span>
            <time dateTime={share.shared_at} title={share.shared_at}>
              {formatInstant(share.shared_at, lng, 'medium', user?.timezone)}
            </time>
            {!share.complete && (
              <Badge variant="outline" className="text-xs">
                {t('settings.capability_share.shared_partial')}
              </Badge>
            )}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}
