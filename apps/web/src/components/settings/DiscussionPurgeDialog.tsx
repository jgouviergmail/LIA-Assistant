'use client';

import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { useProactiveDiscussions } from '@/hooks/useProactiveDiscussions';
import { Button } from '@/components/ui/button';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogFooter,
  AlertDialogCancel,
} from '@/components/ui/alert-dialog';

export interface DiscussionPurgeReview {
  scope: 'all' | string[];
  expected_epoch: number;
  expected_generation: number;
  affected_count: number | null;
  pending: boolean;
  failed: boolean;
  token: number;
}
type Controls = Pick<
  ReturnType<typeof useProactiveDiscussions>,
  'saving' | 'error' | 'contextAction'
>;

export function DiscussionPurgeDialog({
  lng,
  review,
  controls,
  onClose,
  restoreFocus,
}: {
  lng: Language;
  review: DiscussionPurgeReview | null;
  controls: Controls;
  onClose: () => void;
  restoreFocus: () => void;
}) {
  return (
    <AlertDialog
      open={review !== null}
      onOpenChange={open => {
        if (!open && !controls.saving) onClose();
      }}
    >
      <AlertDialogContent
        onCloseAutoFocus={event => {
          event.preventDefault();
          restoreFocus();
        }}
      >
        {review && <PurgeReview lng={lng} review={review} controls={controls} onClose={onClose} />}
      </AlertDialogContent>
    </AlertDialog>
  );
}

function PurgeReview({
  lng,
  review,
  controls,
  onClose,
}: {
  lng: Language;
  review: DiscussionPurgeReview;
  controls: Controls;
  onClose: () => void;
}) {
  const { t } = useTranslation(lng);
  const blocked = controls.saving || review.pending || review.failed;
  async function confirm() {
    if (blocked) return;
    const saved = await controls.contextAction(
      'purge',
      review.scope === 'all' ? undefined : review.scope,
      { expected_epoch: review.expected_epoch, expected_generation: review.expected_generation }
    );
    if (saved) onClose();
  }
  return (
    <>
      <AlertDialogHeader>
        <AlertDialogTitle>{t('discussions.purge_title')}</AlertDialogTitle>
        <AlertDialogDescription>{t('discussions.purge_hint')}</AlertDialogDescription>
        {review.pending && <p role="status">{t('common.loading')}</p>}
        {review.affected_count !== null && (
          <p role="status">{t('discussions.purge_scope', { count: review.affected_count })}</p>
        )}
        {(review.failed || controls.error) && (
          <p role="alert" className="text-sm text-destructive">
            {t('discussions.load_error')}
          </p>
        )}
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel aria-disabled={controls.saving}>{t('common.cancel')}</AlertDialogCancel>
        <Button
          variant="destructive"
          disabled={blocked}
          aria-disabled={controls.saving}
          onClick={() => void confirm()}
        >
          {t('discussions.confirm_purge')}
        </Button>
      </AlertDialogFooter>
    </>
  );
}
