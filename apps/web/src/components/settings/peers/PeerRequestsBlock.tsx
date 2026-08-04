'use client';

/**
 * PeerRequestsBlock — pending requests, incoming and outgoing (spec §5.2).
 *
 * Incoming rows carry accept / decline / block; the requester's context note
 * renders as plain quoted TEXT (third-party content — never markup).
 * Outgoing rows only show the waiting state: no cancel in v1 (requests
 * expire server-side).
 */

import { Inbox } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { lifecycleTone } from '@/lib/status-tone';
import type { ConnectionView } from '@/hooks/usePeerConnections';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerRequestsBlockProps {
  lng: Language;
  requests: ConnectionView[];
  mutating: boolean;
  onRespond: (connectionId: string, accept: boolean) => Promise<boolean>;
  onBlock: (peerId: string) => Promise<boolean>;
}

export function PeerRequestsBlock({
  lng,
  requests,
  mutating,
  onRespond,
  onBlock,
}: PeerRequestsBlockProps) {
  const { t } = useTranslation(lng);

  return (
    <div className="space-y-2">
      {/* Sub-title inside the "find someone" fold — icon in theme colour,
          never grey (owner rule 2026-08-05: a title always carries an icon,
          and a title icon is never muted). */}
      <h4 className="flex items-center gap-2 text-sm font-medium">
        <Inbox className="h-4 w-4 text-primary" aria-hidden="true" />
        {t('settings.peers.requests.title')}
      </h4>
      {requests.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('settings.peers.requests.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {requests.map(request => (
            <li key={request.id} className="space-y-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{request.peer_display_name}</p>
                  <p className="text-xs text-muted-foreground">{request.peer_email_hint}</p>
                </div>
                {request.direction === 'outgoing' && (
                  // A pending request is a LIVE state, so it takes its tone
                  // from the shared lifecycle table — grey badges are
                  // reserved for inactive elements (owner rule 2026-08-05).
                  <Badge variant={lifecycleTone('pending')}>
                    {t('settings.peers.requests.outgoing_badge')}
                  </Badge>
                )}
              </div>
              {request.direction === 'incoming' && request.context_message && (
                <blockquote className="border-l-2 pl-2 text-sm text-muted-foreground">
                  {request.context_message}
                </blockquote>
              )}
              {request.direction === 'incoming' && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={mutating}
                    onClick={() => void onRespond(request.id, true)}
                  >
                    {t('settings.peers.requests.accept')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={mutating}
                    onClick={() => void onRespond(request.id, false)}
                  >
                    {t('settings.peers.requests.decline')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    disabled={mutating}
                    onClick={() => void onBlock(request.peer_id)}
                  >
                    {t('settings.peers.requests.block')}
                  </Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
