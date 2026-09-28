'use client';

/**
 * « Send by e-mail » on a card of the chat, the gallery or the bookmarks (ADR-321).
 *
 * Self-gated: it renders nothing unless the page offers the action
 * (`EmailShareAvailabilityProvider`). The file to send, the dialog and the
 * request for the account's options inside it only exist once the button is
 * pressed, so a conversation of twenty cards costs nothing until someone sends
 * one.
 *
 * Three presentations, each matching its neighbours: a round action over an
 * image (`overlay`), a ghost icon button in the gallery and the bookmarks
 * (`ghost`), a chip in an answer's action row (`chip`).
 */

import { useState, type MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Mail } from 'lucide-react';

import { ActionChipButton } from '@/components/chat/ActionChipButton';
import { EmailShareDialog } from '@/components/email-share/EmailShareDialog';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useEmailShareAvailable } from '@/lib/email-share/availability-context';
import type { EmailShareSource } from '@/lib/email-share/share';

export interface EmailShareButtonProps {
  /**
   * What is sent — built when the button is PRESSED, never at render: an
   * answer's export flattens its HTML, and this row renders on every bubble.
   */
  getSource: () => EmailShareSource;
  /** The subject the dialog proposes. */
  defaultSubject: string;
  /** How the trigger looks, to match its neighbours. */
  variant: 'overlay' | 'ghost' | 'chip';
  /** The overlay's round-button style (the neighbouring download button's). */
  className?: string;
  /** Names the file in the accessible name, where several cards sit side by side. */
  labelName?: string;
}

export function EmailShareButton({
  getSource,
  defaultSubject,
  variant,
  className,
  labelName,
}: EmailShareButtonProps) {
  const { t } = useTranslation();
  const available = useEmailShareAvailable();
  // Null while closed: the source exists only for the dialog that sends it.
  const [source, setSource] = useState<EmailShareSource | null>(null);
  if (!available) return null;

  const label = labelName
    ? t('email_share.button_named', { name: labelName })
    : t('email_share.button');
  const openDialog = (event: MouseEvent) => {
    // Over an image the card itself opens a lightbox: the click stays ours.
    event.stopPropagation();
    setSource(getSource());
  };

  return (
    <>
      {variant === 'chip' && (
        <ActionChipButton label={label} onClick={openDialog}>
          <Mail className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
        </ActionChipButton>
      )}
      {variant === 'ghost' && (
        <Button variant="ghost" size="sm" onClick={openDialog} aria-label={label}>
          <Mail className="h-3.5 w-3.5" aria-hidden="true" />
        </Button>
      )}
      {variant === 'overlay' && (
        <Tooltip>
          <TooltipTrigger asChild>
            <button type="button" onClick={openDialog} className={className} aria-label={label}>
              <Mail className="h-4 w-4" aria-hidden="true" />
            </button>
          </TooltipTrigger>
          <TooltipContent>{label}</TooltipContent>
        </Tooltip>
      )}
      {source !== null && (
        <EmailShareDialog
          open
          onOpenChange={isOpen => {
            if (!isOpen) setSource(null);
          }}
          source={source}
          defaultSubject={defaultSubject}
        />
      )}
    </>
  );
}
