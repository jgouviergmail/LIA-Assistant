'use client';

/**
 * "LIA is on the phone" (A6, second half).
 *
 * The first half of A6 put the call history in the settings — useful after the
 * fact, useless during. And during is exactly when the user is looking: they
 * confirm a call, stay in the chat, and until now the product went completely
 * silent. Nothing said LIA was dialing, nothing said it was still talking.
 *
 * So this is a thin band above the thread, visible ONLY while a call is in
 * flight, and gone the moment it ends. It states what LIA is doing and for
 * whom, and links to the recap surface.
 *
 * It deliberately does NOT go through `lib/chat-surfaces`: that arbiter owns
 * the single exclusive slot above the composer (approval, usage wall, HITL…),
 * where surfaces compete. This one competes with nothing — it is a status
 * line, like the quota banner it sits next to, and losing the slot to a
 * pending approval would hide exactly the information the user is waiting for.
 */

import { useEffect } from 'react';

import Link from 'next/link';
import { PhoneCall } from 'lucide-react';

import { useTranslation } from 'react-i18next';

import { useTelephonyCalls } from '@/hooks/useTelephonyCalls';
import { settingsSectionHref } from '@/lib/settings-sections';
import { ACTIVE_CALL_STATUSES } from '@/types/telephony';

export interface ActiveCallBannerProps {
  /** Current URL locale segment. */
  lng: string;
  /**
   * Anything that changes when the conversation advances (a message count).
   *
   * Load-bearing: the hook only polls WHILE a call is in flight, so a chat
   * opened BEFORE the call sees an empty list and never polls again — the band
   * could never appear, which is exactly how it failed in practice. A call is
   * always born from a conversation turn, so re-reading on every turn catches
   * its start without polling an idle account forever.
   */
  conversationTick?: number;
}

export function ActiveCallBanner({ lng, conversationTick = 0 }: ActiveCallBannerProps) {
  const { t } = useTranslation();
  const { calls, hasActiveCall, refetch } = useTelephonyCalls();

  useEffect(() => {
    // Skip the mount read: the hook already did it.
    if (conversationTick > 0) void refetch();
  }, [conversationTick, refetch]);

  if (!hasActiveCall) return null;

  const active = calls.find(call => ACTIVE_CALL_STATUSES.includes(call.status));
  if (!active) return null;

  return (
    // Polite: the user is mid-conversation. Worth announcing, not interrupting.
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-2 gap-y-1 border-b border-primary/25 bg-primary/10 px-4 py-2 text-xs"
    >
      <PhoneCall className="h-3.5 w-3.5 shrink-0 animate-pulse text-primary" aria-hidden="true" />
      <span className="font-semibold text-primary">
        {t(`chat.active_call.${active.status}`, { name: active.callee_display })}
      </span>
      <span className="text-muted-foreground">{active.objective}</span>
      <Link
        href={settingsSectionHref(lng, 'telephony-calls')}
        className="ml-auto font-medium text-primary underline decoration-primary/40 underline-offset-2 hover:decoration-primary rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {t('chat.active_call.details')}
      </Link>
    </div>
  );
}
