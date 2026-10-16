'use client';

/**
 * PeerRequestsBlock — pending requests, incoming and outgoing (spec §5.2).
 *
 * Incoming rows carry accept / decline / block; the requester's context note
 * renders as plain quoted TEXT (third-party content — never markup).
 * Outgoing rows only show the waiting state: no cancel in v1 (requests
 * expire server-side).
 */

import { useRef, useState } from 'react';
import { Check, ShieldOff, X } from 'lucide-react';
import { Avatar } from '@/components/ui/avatar';

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
  onResolved?: () => void;
}

export function PeerRequestsBlock({
  lng,
  requests,
  mutating,
  onRespond,
  onBlock,
  onResolved,
}: PeerRequestsBlockProps) {
  const { t } = useTranslation(lng);
  const lock = useRef(false);
  const [pending, setPending] = useState(false);
  const busy = mutating || pending;
  const perform = async (operation: () => Promise<boolean>) => {
    if (mutating || lock.current) return;
    lock.current = true;
    setPending(true);
    try {
      if (await operation()) onResolved?.();
    } finally {
      lock.current = false;
      setPending(false);
    }
  };

  return (
    <div className="space-y-2">
      {requests.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t('settings.peers.requests.empty')}</p>
      ) : (
        <ul className="space-y-2">
          {requests.map(request => (
            <li
              key={request.id}
              className="space-y-3 rounded-xl border border-border/50 bg-card p-4 [--lia-field-background:var(--color-background)]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-3">
                  <Avatar
                    name={request.peer_display_name}
                    size="sm"
                    disableHover
                    className="shrink-0"
                  />
                  <div className="min-w-0">
                    <p className="break-words text-sm font-medium">{request.peer_display_name}</p>
                    <p className="break-all text-xs text-muted-foreground">
                      {request.peer_email_hint}
                    </p>
                  </div>
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
                <blockquote className="break-words rounded-lg bg-primary/5 p-3 text-sm leading-relaxed text-muted-foreground">
                  {request.context_message}
                </blockquote>
              )}
              {request.direction === 'incoming' && (
                <div className="flex flex-col items-stretch gap-2 border-t border-border/40 pt-3 sm:items-start">
                  <Button
                    type="button"
                    size="sm"
                    aria-disabled={busy}
                    onClick={() => void perform(() => onRespond(request.id, true))}
                  >
                    <Check aria-hidden="true" />
                    {t('settings.peers.requests.accept')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    aria-disabled={busy}
                    onClick={() => void perform(() => onRespond(request.id, false))}
                  >
                    <X aria-hidden="true" />
                    {t('settings.peers.requests.decline')}
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="default"
                    aria-disabled={busy}
                    onClick={() => void perform(() => onBlock(request.peer_id))}
                  >
                    <ShieldOff aria-hidden="true" />
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
