'use client';

/**
 * « Share with a connection » on a generated image card of the chat (ADR-316).
 *
 * Self-gated: it renders nothing unless the chat offers the action
 * (`PeersAvailabilityProvider`), the card points at one of our attachments — an
 * external image cannot be shared — and the image has not expired (the card
 * already says so; a share would only be refused). The dialog, and the request
 * for the person's connections inside it, only exist once the button is pressed.
 */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Send } from 'lucide-react';

import { ShareImageDialog } from '@/components/peers/ShareImageDialog';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { classifyImageExpiry } from '@/lib/image-expiry';
import { usePeersAvailable } from '@/lib/peers/availability-context';
import { attachmentIdFromUrl } from '@/lib/peers/image-share';

export interface ShareImageButtonProps {
  /** The card's URL, as the API emitted it. */
  url: string;
  /** What the image is called (its alt text, the request that produced it). */
  title: string;
  /** The card's deadline; an expired image is not offered. */
  expiresAt?: string | null;
  /** The overlay button style the neighbouring download button uses. */
  className: string;
}

export function ShareImageButton({ url, title, expiresAt, className }: ShareImageButtonProps) {
  const { t } = useTranslation();
  const enabled = usePeersAvailable();
  const [open, setOpen] = useState(false);
  const attachmentId = attachmentIdFromUrl(url);
  const expired = classifyImageExpiry(expiresAt, new Date()).kind === 'expired';
  if (!enabled || attachmentId === null || expired) return null;

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={event => {
              event.stopPropagation();
              setOpen(true);
            }}
            className={className}
            aria-label={t('settings.peers.share_image.button')}
          >
            <Send className="h-4 w-4" aria-hidden="true" />
          </button>
        </TooltipTrigger>
        <TooltipContent>{t('settings.peers.share_image.button')}</TooltipContent>
      </Tooltip>
      {open && (
        <ShareImageDialog
          open={open}
          onOpenChange={setOpen}
          attachmentId={attachmentId}
          imageTitle={title}
        />
      )}
    </>
  );
}
