'use client';

/**
 * PeerMessageActions — quick actions under peer chat bubbles (peers Lot 7).
 *
 * Self-contained metadata-driven block (PhoneCallDebriefBlock precedent):
 * renders nothing unless the bubble is a peer notification. The metadata is
 * parsed once into a typed context (module-level — CC discipline), then each
 * flow lives in its own subcomponent:
 *
 * - `proactive_peer_message` → Reply (prefills the composer — A4 contract:
 *   prefill NEVER sends) + Block (house confirm, then POST /peers/blocks).
 * - `proactive_peer_request` (incoming request) → Accept / Decline
 *   (POST /peers/requests/{id}/respond) — one-click from the chat, mirroring
 *   the settings section. After a response the chips freeze into the verdict.
 *
 * Errors surface through the shared `peers_*` code→toast mapping.
 */

import { useState } from 'react';
import { Check, Reply, ShieldOff, X } from 'lucide-react';
import { toast } from 'sonner';

import { useConfirm } from '@/components/ui/use-confirm';
import { toastPeersError } from '@/components/settings/peers/peers-error-messages';
import { useApiMutation } from '@/hooks/useApiMutation';
import { ApiError } from '@/lib/api-client';
import { useTranslation } from 'react-i18next';

export interface PeerMessageActionsProps {
  metadata: Record<string, unknown> | undefined;
  /** Chat-page composer prefill (chipPrefill contract — never sends). */
  onPrefillComposer?: (text: string) => void;
}

type PeerActionContext =
  | { kind: 'message'; peerId: string | null; peerName: string }
  | { kind: 'request'; connectionId: string | null; peerName: string };

/** Read one string metadata field, or null when absent/mistyped. */
function str(metadata: Record<string, unknown>, key: string): string | null {
  const value = metadata[key];
  return typeof value === 'string' ? value : null;
}

/**
 * Parse the bubble metadata into an actionable peer context, or null.
 *
 * Only INCOMING requests are actionable; outcome/removal notices share the
 * peer_connection task type and carry a non-request peer_event kind.
 */
function parsePeerActionContext(
  metadata: Record<string, unknown> | undefined
): PeerActionContext | null {
  if (!metadata) return null;
  if (metadata.type === 'proactive_peer_message') {
    return {
      kind: 'message',
      peerId: str(metadata, 'sender_id') ?? str(metadata, 'peer_id'),
      peerName: str(metadata, 'sender_name') ?? str(metadata, 'peer_name') ?? '',
    };
  }
  if (metadata.type === 'proactive_peer_request' && metadata.peer_event === 'request_created') {
    return {
      kind: 'request',
      connectionId: str(metadata, 'target_id'),
      peerName: str(metadata, 'peer_name') ?? '',
    };
  }
  return null;
}

/** Extract the stable `peers_*` code from a thrown mutation error. */
function errorCode(err: unknown): string | null {
  if (err instanceof ApiError && err.data && typeof err.data === 'object') {
    const detail = (err.data as { detail?: unknown }).detail;
    if (typeof detail === 'string') return detail;
  }
  return null;
}

const CHIP =
  'inline-flex items-center gap-1.5 rounded-md border border-border/30 bg-background/80 ' +
  'px-2 py-1 text-xs font-medium text-foreground/90 hover:bg-background transition-colors ' +
  'disabled:opacity-50 disabled:cursor-not-allowed';

/** Reply (composer prefill) + Block (confirmed) under a relayed message. */
function RelayedMessageActions({
  context,
  onPrefillComposer,
}: {
  context: Extract<PeerActionContext, { kind: 'message' }>;
  onPrefillComposer?: (text: string) => void;
}) {
  const { t } = useTranslation();
  const { confirm, confirmDialog } = useConfirm();
  const post = useApiMutation({ method: 'POST', componentName: 'PeerMessageActions' });
  const [blocked, setBlocked] = useState(false);

  const handleReply = () => {
    onPrefillComposer?.(t('chat.peer.reply_prefill', { name: context.peerName || '…' }));
  };

  const handleBlock = async () => {
    if (!context.peerId) return;
    const accepted = await confirm({
      title: t('settings.peers.connections.block_confirm_title'),
      description: t('settings.peers.connections.block_confirm_description'),
    });
    if (!accepted) return;
    try {
      await post.mutate('/peers/blocks', { peer_id: context.peerId });
      setBlocked(true);
      toast.success(t('settings.peers.blocks.blocked'));
    } catch (err) {
      toastPeersError(t, errorCode(err));
    }
  };

  return (
    <>
      {confirmDialog}
      <button type="button" onClick={handleReply} className={CHIP}>
        <Reply className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        {t('chat.peer.reply')}
      </button>
      {context.peerId && !blocked && (
        <button
          type="button"
          onClick={() => void handleBlock()}
          disabled={post.loading}
          className={CHIP}
        >
          <ShieldOff className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
          {t('chat.peer.block')}
        </button>
      )}
    </>
  );
}

/** Accept/Decline chips under an incoming connection request. */
function ConnectionRequestActions({
  context,
}: {
  context: Extract<PeerActionContext, { kind: 'request' }>;
}) {
  const { t } = useTranslation();
  const post = useApiMutation({ method: 'POST', componentName: 'PeerMessageActions' });
  const [responded, setResponded] = useState<'accepted' | 'declined' | null>(null);

  const handleRespond = async (accept: boolean) => {
    if (!context.connectionId) return;
    try {
      await post.mutate(`/peers/requests/${context.connectionId}/respond`, { accept });
      setResponded(accept ? 'accepted' : 'declined');
      toast.success(
        accept ? t('settings.peers.requests.accepted') : t('settings.peers.requests.declined')
      );
    } catch (err) {
      toastPeersError(t, errorCode(err));
    }
  };

  if (responded) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-muted-foreground">
        {responded === 'accepted' ? (
          <Check className="h-3.5 w-3.5 text-green-600" aria-hidden="true" />
        ) : (
          <X className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        )}
        {responded === 'accepted'
          ? t('settings.peers.requests.accepted')
          : t('settings.peers.requests.declined')}
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        onClick={() => void handleRespond(true)}
        disabled={post.loading || !context.connectionId}
        className={CHIP}
      >
        <Check className="h-3.5 w-3.5 text-green-600" aria-hidden="true" />
        {t('settings.peers.requests.accept')}
      </button>
      <button
        type="button"
        onClick={() => void handleRespond(false)}
        disabled={post.loading || !context.connectionId}
        className={CHIP}
      >
        <X className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        {t('settings.peers.requests.decline')}
      </button>
    </>
  );
}

export function PeerMessageActions({ metadata, onPrefillComposer }: PeerMessageActionsProps) {
  const context = parsePeerActionContext(metadata);
  if (context === null) return null;
  if (context.kind === 'message') {
    return <RelayedMessageActions context={context} onPrefillComposer={onPrefillComposer} />;
  }
  return <ConnectionRequestActions context={context} />;
}
