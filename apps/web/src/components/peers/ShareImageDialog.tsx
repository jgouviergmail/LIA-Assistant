'use client';

/**
 * Share one generated image with a connection (ADR-316).
 *
 * The click on « share » opens this dialog, and the dialog's own button IS the
 * confirmation: the person picks who receives it and may add a few words. The
 * recipient gets a COPY in their images, as if they had generated it when it
 * arrived, and a bubble in their chat that shows it with the comment quoted.
 *
 * Three states are told apart on purpose: « still loading », « could not be
 * read » and « no connection yet » — an empty list read as "no connection"
 * when the request merely failed would be a false statement about the account.
 */

import { useCallback, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Loader2, Send } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { peersErrorCode, toastPeersError } from '@/components/settings/peers/peers-error-messages';
import { usePeerRecipientsState } from '@/hooks/usePeerRecipients';
import apiClient from '@/lib/api-client';
import { IMAGE_SHARE_COMMENT_MAX_CHARS } from '@/lib/peers/image-share';
import { PeerRecipientList } from './PeerRecipientList';

/** What `POST /peers/connections/{id}/images` answers. */
interface ImageShareView {
  id: string;
  recipient_display_name: string;
  /** False when only the recipient's notification failed — the copy is theirs anyway. */
  delivered: boolean;
}

export interface ShareImageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The attachment the image card shows — one of the person's generated images. */
  attachmentId: string;
  /** What the image is called, so the person knows which one they are sharing. */
  imageTitle: string;
}

export function ShareImageDialog({
  open,
  onOpenChange,
  attachmentId,
  imageTitle,
}: ShareImageDialogProps) {
  const { t } = useTranslation();
  const { recipients, loading, error } = usePeerRecipientsState(open);
  const [connectionId, setConnectionId] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  const [sending, setSending] = useState(false);
  const groupName = useId();
  const counterId = useId();

  const close = useCallback(
    (isOpen: boolean) => {
      if (!isOpen) {
        setConnectionId(null);
        setComment('');
      }
      onOpenChange(isOpen);
    },
    [onOpenChange]
  );

  const share = async () => {
    if (!connectionId || sending) return;
    setSending(true);
    try {
      const view = await apiClient.post<ImageShareView>(
        `/peers/connections/${connectionId}/images`,
        { attachment_id: attachmentId, comment: comment.trim() || null }
      );
      toast.success(
        t('settings.peers.share_image.shared', { name: view.recipient_display_name }),
        view.delivered ? undefined : { description: t('settings.peers.share_image.not_notified') }
      );
      close(false);
    } catch (err) {
      toastPeersError(t, peersErrorCode(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Send className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.peers.share_image.title')}
          </DialogTitle>
          <DialogDescription>{t('settings.peers.share_image.description')}</DialogDescription>
        </DialogHeader>

        {/* Which image: the title is the request that produced it. */}
        <p className="line-clamp-2 break-words text-sm font-medium" title={imageTitle}>
          {imageTitle}
        </p>

        <fieldset className="space-y-2" disabled={sending}>
          <legend className="text-sm font-medium">
            {t('settings.peers.share_image.recipient')}
          </legend>
          <PeerRecipientList
            loading={loading}
            failed={error !== null}
            recipients={recipients}
            groupName={groupName}
            selected={connectionId}
            onSelect={setConnectionId}
          />
        </fieldset>

        {recipients.length > 0 && (
          <div className="space-y-1">
            <Textarea
              label={t('settings.peers.share_image.comment_label')}
              placeholder={t('settings.peers.share_image.comment_placeholder')}
              value={comment}
              maxLength={IMAGE_SHARE_COMMENT_MAX_CHARS}
              onChange={event => setComment(event.target.value)}
              aria-describedby={counterId}
              disabled={sending}
              rows={3}
            />
            <p id={counterId} className="text-right text-xs text-foreground/80">
              {t('settings.peers.share_image.characters', {
                count: comment.length,
                max: IMAGE_SHARE_COMMENT_MAX_CHARS,
              })}
            </p>
          </div>
        )}

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="outline" onClick={() => close(false)} disabled={sending}>
            {t('common.cancel')}
          </Button>
          <Button onClick={() => void share()} disabled={!connectionId || sending}>
            {sending && <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" />}
            {t('settings.peers.share_image.submit')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
