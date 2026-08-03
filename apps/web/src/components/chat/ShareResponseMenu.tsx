import { useCallback, useState } from 'react';
import { Download, MoreHorizontal, Share2, Users } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { usePeerRecipients } from '@/hooks/usePeerRecipients';
import { messageToPlainText } from '@/lib/message-clipboard';
import { downloadMarkdown } from '@/lib/utils/download-markdown';

/** Two-digit zero-pad for the filename date components. */
function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** `lia-YYYY-MM-DD-HH-mm`, stamped from the user's local clock. */
function exportBaseName(timestamp: Date): string {
  const date = `${timestamp.getFullYear()}-${pad2(timestamp.getMonth() + 1)}-${pad2(timestamp.getDate())}`;
  return `lia-${date}-${pad2(timestamp.getHours())}-${pad2(timestamp.getMinutes())}`;
}

export interface ShareResponseMenuProps {
  /**
   * Raw assistant response content — markdown, or a `lia-response` HTML
   * document in `html` display mode. HTML is flattened to readable text
   * before sharing/exporting (ADR-177); markdown passes through verbatim.
   */
  content: string;
  /** When the response landed — stamps the export filename (local time). */
  timestamp: Date;
  /**
   * Put text in the composer, without sending it.
   *
   * Absent on surfaces that have no composer (an archived read-only view);
   * the peer-share entry then hides rather than leading nowhere.
   */
  onPrefillComposer?: (text: string) => void;
}

/**
 * "…" menu at the end of the assistant bubble action row (UX P4): the
 * platform share sheet where `navigator.share` exists, and a dated `.md`
 * export everywhere. Share availability is FEATURE detection, never platform
 * sniffing — desktop Chrome/Edge on Windows expose `navigator.share` too.
 * Non-modal like every navigation menu (ADR-171: modal Radix menus turn
 * `body` into a scrollport and break sticky headers).
 */
export function ShareResponseMenu({
  content,
  timestamp,
  onPrefillComposer,
}: ShareResponseMenuProps) {
  const { t } = useTranslation();
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  // Fetched only while the menu is OPEN. This component renders on every
  // assistant bubble: reading the settings panel's five-query hook here cost
  // 120 requests on a twelve-answer conversation (measured 2026-08-03).
  const [open, setOpen] = useState(false);
  const peers = usePeerRecipients(open);
  const canRelay = Boolean(onPrefillComposer) && peers.length > 0;

  // Relaying is not a browser capability. `send_peer_message` returns a draft
  // the user must confirm and delivery is assistant-to-assistant, so this
  // writes the REQUEST into the composer and lets it take the ordinary road —
  // HITL confirmation included. Posting the relay from here would bypass that,
  // and the capability channel is read-only by design.
  const relayTo = useCallback(
    (recipient: string) => {
      onPrefillComposer?.(
        t('chat.message.share_peer_draft', {
          recipient,
          content: messageToPlainText(content),
        })
      );
    },
    [content, onPrefillComposer, t]
  );

  const handleShare = useCallback(async () => {
    try {
      await navigator.share({ title: 'LIA', text: messageToPlainText(content) });
    } catch (err) {
      // A dismissed share sheet reports AbortError — a non-event, not a failure.
      if (err instanceof DOMException && err.name === 'AbortError') return;
      toast.error(t('chat.message.share_error'));
    }
  }, [content, t]);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label={t('chat.message.more_actions')}
          className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background transition-colors"
        >
          <MoreHorizontal className="h-3.5 w-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {canShare && (
          <DropdownMenuItem onSelect={() => void handleShare()}>
            <Share2 className="text-muted-foreground" />
            {t('chat.message.share')}
          </DropdownMenuItem>
        )}
        <DropdownMenuItem
          onSelect={() => downloadMarkdown(messageToPlainText(content), exportBaseName(timestamp))}
        >
          <Download className="text-muted-foreground" />
          {t('chat.message.download_md')}
        </DropdownMenuItem>
        {/* Flat, not a submenu: a nested dropdown is awkward under a thumb,
            and the recipients are few. The label says what the names below
            are for, so a peer's name is never a bare, unexplained entry. */}
        {canRelay && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
              <Users className="h-3.5 w-3.5" aria-hidden="true" />
              {t('chat.message.share_peer')}
            </DropdownMenuLabel>
            {peers.map(peer => (
              <DropdownMenuItem key={peer.id} onSelect={() => relayTo(peer.peer_display_name)}>
                {peer.peer_display_name}
              </DropdownMenuItem>
            ))}
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
