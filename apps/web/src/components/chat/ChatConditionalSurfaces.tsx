'use client';

/**
 * The conditional surfaces stacked between the message thread and the composer.
 *
 * Four blocks compete for that band — follow-up chips, the geolocation prompt,
 * the HITL approval card and connector notices. Which of them may take the slot
 * is decided by the pure arbiter in `lib/chat-surfaces` (S1); this component
 * only renders that decision, so the chat page keeps a single element here
 * instead of four independent branches.
 *
 * A surface that does not hold the slot is UNMOUNTED, not hidden: it then costs
 * neither vertical space nor work. Two of them are deliberately unconditional:
 *
 * - `HitlActionCard` is blocking, and it also carries the resolved/expired
 *   end-of-life badges — states the arbiter's `hitlAwaitingAction` excludes on
 *   purpose. It owns its own `status === 'none'` early return.
 * - `ConnectorNoticeBanner` explains why an answer is incomplete; it renders
 *   nothing (not even padding) without notices.
 */

import { FollowupChips, type FollowupChipsProps } from '@/components/chat/FollowupChips';
import { GeolocationPrompt } from '@/components/chat/GeolocationPrompt';
import { HitlActionCard, type HitlActionCardProps } from '@/components/chat/HitlActionCard';
import {
  ConnectorNoticeBanner,
  type ConnectorNoticeBannerProps,
} from '@/components/chat/ConnectorNoticeBanner';
import type { ChatSurface } from '@/lib/chat-surfaces';

export interface ChatConditionalSurfacesProps {
  /** The arbiter's decision (see `visibleChatSurfaces`). */
  surfaces: ReadonlySet<ChatSurface>;
  /** Suggestions of the latest answer — already filtered for staleness. */
  followupSuggestions: FollowupChipsProps['suggestions'];
  /** A chip click PREFILLS the composer; it never sends (A2 contract). */
  onFollowupPick: FollowupChipsProps['onPick'];
  /** Current composer text — the geolocation prompt derives its own trigger. */
  currentMessage: string;
  hitl: HitlActionCardProps['hitl'];
  onHitlAction: HitlActionCardProps['onAction'];
  connectorNotices: ConnectorNoticeBannerProps['notices'];
  onDismissConnectorNotice: ConnectorNoticeBannerProps['onDismiss'];
}

export function ChatConditionalSurfaces({
  surfaces,
  followupSuggestions,
  onFollowupPick,
  currentMessage,
  hitl,
  onHitlAction,
  connectorNotices,
  onDismissConnectorNotice,
}: ChatConditionalSurfacesProps) {
  return (
    <>
      {surfaces.has('followups') && (
        <FollowupChips suggestions={followupSuggestions} onPick={onFollowupPick} />
      )}

      {surfaces.has('geolocation') && <GeolocationPrompt currentMessage={currentMessage} />}

      <HitlActionCard hitl={hitl} onAction={onHitlAction} />

      <ConnectorNoticeBanner notices={connectorNotices} onDismiss={onDismissConnectorNotice} />
    </>
  );
}
