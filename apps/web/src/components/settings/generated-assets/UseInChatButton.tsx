'use client';

/**
 * « Use in the discussion » — what LIA gave comes back into the chat (2026-10-24).
 *
 * A plain link to the chat's `?attach=`: the composer asks the API for a COPY
 * and shows it in its strip, where the person reviews it before sending.
 * Nothing is sent by the click. Drawn only where the instance takes
 * attachments: elsewhere the link would arrive at a composer that cannot
 * hold the copy.
 */

import { MessageSquarePlus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { useAppConfig } from '@/hooks/useAppConfig';
import type { AttachSource } from '@/lib/attach-source-link';
import { chatAttachHref } from '@/lib/briefing-utils';
import { openChatDeepLink } from '@/lib/chat-deep-link';

export function UseInChatButton({
  lng,
  source,
  label,
}: {
  lng: string;
  source: AttachSource;
  /** Already translated: names what joins the discussion. */
  label: string;
}) {
  const { config } = useAppConfig();
  if (config?.features?.attachments_enabled === false) return null;
  return (
    <Button
      variant="ghost"
      size="sm"
      onClick={() => openChatDeepLink(chatAttachHref(lng, source))}
      aria-label={label}
      title={label}
    >
      <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
    </Button>
  );
}
