/**
 * « Share » and « Download » at the end of the assistant bubble action row.
 *
 * They replaced a « … » menu that hid both behind one more click (owner
 * request, 2026-09-24):
 *
 * - **Download** is one click everywhere: the answer as a dated `.md` file.
 * - **Share** is one click too when the platform share sheet is the only way
 *   out. Its availability is FEATURE detection, never platform sniffing —
 *   desktop Chrome/Edge on Windows expose `navigator.share` too.
 * - When a connection can also receive the answer (the chat's composer is
 *   there and the instance offers connections), Share opens a menu: the
 *   platform sheet, then the accepted connections. Relaying is not a browser
 *   capability: `send_peer_message` returns a draft the person confirms, so
 *   picking a connection PREFILLS the composer and the request takes the
 *   ordinary road, HITL confirmation included.
 *
 * The connections are read only while that menu is open: this row renders on
 * every assistant bubble, and a closed menu on twenty bubbles must cost
 * nothing (measured once at 120 requests on a twelve-answer conversation).
 * Non-modal like every navigation menu (ADR-171: a modal Radix menu turns
 * `body` into a scrollport and breaks the sticky headers).
 */

import { useCallback, useState, type ReactNode } from 'react';
import { Download, Share2, Users } from 'lucide-react';
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
import { usePeerRecipientsState } from '@/hooks/usePeerRecipients';
import type { ConnectionView } from '@/hooks/usePeerConnections';
import { messageToPlainText } from '@/lib/message-clipboard';
import { usePeersAvailable } from '@/lib/peers/availability-context';
import { connectionsSettingsPath } from '@/lib/peers/recipients';
import { downloadMarkdown } from '@/lib/utils/download-markdown';

import { ActionChipButton } from './ActionChipButton';

/** Two-digit zero-pad for the filename date components. */
function pad2(value: number): string {
  return String(value).padStart(2, '0');
}

/** `lia-YYYY-MM-DD-HH-mm`, stamped from the user's local clock. */
function exportBaseName(timestamp: Date): string {
  const date = `${timestamp.getFullYear()}-${pad2(timestamp.getMonth() + 1)}-${pad2(timestamp.getDate())}`;
  return `lia-${date}-${pad2(timestamp.getHours())}-${pad2(timestamp.getMinutes())}`;
}

const ICON_CLASS = 'h-3.5 w-3.5 text-muted-foreground';

export interface ShareResponseActionsProps {
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
   * relaying to a connection is then not offered rather than leading nowhere.
   */
  onPrefillComposer?: (text: string) => void;
}

export function ShareResponseActions({
  content,
  timestamp,
  onPrefillComposer,
}: ShareResponseActionsProps) {
  const { t } = useTranslation();
  const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function';
  const peersAvailable = usePeersAvailable();
  const canRelay = Boolean(onPrefillComposer) && peersAvailable;

  const handleShare = useCallback(async () => {
    try {
      await navigator.share({ title: 'LIA', text: messageToPlainText(content) });
    } catch (err) {
      // A dismissed share sheet reports AbortError — a non-event, not a failure.
      if (err instanceof DOMException && err.name === 'AbortError') return;
      toast.error(t('chat.message.share_error'));
    }
  }, [content, t]);

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

  const shareLabel = t('chat.message.share');
  let share: ReactNode = null;
  if (canRelay) {
    share = (
      <ShareMenu label={shareLabel} canShare={canShare} onShare={handleShare} onRelay={relayTo} />
    );
  } else if (canShare) {
    share = (
      <ActionChipButton label={shareLabel} onClick={() => void handleShare()}>
        <Share2 className={ICON_CLASS} aria-hidden="true" />
      </ActionChipButton>
    );
  }

  return (
    <>
      {share}
      <ActionChipButton
        label={t('chat.message.download_md')}
        onClick={() => downloadMarkdown(messageToPlainText(content), exportBaseName(timestamp))}
      >
        <Download className={ICON_CLASS} aria-hidden="true" />
      </ActionChipButton>
    </>
  );
}

interface ShareMenuProps {
  label: string;
  canShare: boolean;
  onShare: () => Promise<void>;
  onRelay: (recipient: string) => void;
}

/** The platform sheet, then the connections — read only while the menu is open. */
function ShareMenu({ label, canShare, onShare, onRelay }: ShareMenuProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const { recipients, loading, error } = usePeerRecipientsState(open);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <ActionChipButton label={label}>
          <Share2 className={ICON_CLASS} aria-hidden="true" />
        </ActionChipButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start">
        {canShare && (
          <>
            <DropdownMenuItem onSelect={() => void onShare()}>
              <Share2 className="text-muted-foreground" aria-hidden="true" />
              {t('chat.message.share_system')}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        )}
        {/* Flat, not a submenu: a nested dropdown is awkward under a thumb,
            and the recipients are few. The label says what the names below
            are for, so a connection's name is never a bare entry. */}
        <DropdownMenuLabel className="flex items-center gap-2 text-xs font-normal text-muted-foreground">
          <Users className="h-3.5 w-3.5" aria-hidden="true" />
          {t('chat.message.share_peer')}
        </DropdownMenuLabel>
        <RecipientItems
          recipients={recipients}
          loading={loading}
          failed={error !== null}
          onRelay={onRelay}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

interface RecipientItemsProps {
  recipients: ConnectionView[];
  loading: boolean;
  failed: boolean;
  onRelay: (recipient: string) => void;
}

/** The accepted connections, or what stands in their place — never a silent empty list. */
function RecipientItems({ recipients, loading, failed, onRelay }: RecipientItemsProps) {
  const { t } = useTranslation();
  if (recipients.length > 0) {
    return (
      <>
        {recipients.map(peer => (
          <DropdownMenuItem key={peer.id} onSelect={() => onRelay(peer.peer_display_name)}>
            {peer.peer_display_name}
          </DropdownMenuItem>
        ))}
      </>
    );
  }
  let note = t('settings.peers.recipients.no_connection', { path: connectionsSettingsPath(t) });
  if (loading) note = t('settings.peers.recipients.loading');
  else if (failed) note = t('settings.peers.recipients.load_error');
  return (
    <DropdownMenuItem disabled className="max-w-xs whitespace-normal text-xs">
      {note}
    </DropdownMenuItem>
  );
}
