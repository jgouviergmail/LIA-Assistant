'use client';

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { readDiscussionDraft } from '@/hooks/useInputDraft';

export function DiscussionUnavailable({
  ownerId,
  id,
  refused,
  onMain,
  onRetry,
  readReleasedDraft,
}: {
  ownerId: string;
  id: string | null;
  refused: boolean;
  onMain: () => void;
  onRetry: () => void;
  readReleasedDraft: () => string | undefined;
}) {
  const { t } = useTranslation();
  const [draft, setDraft] = useState<string>();
  useEffect(() => {
    // The composer releases its text during passive unmount, before this read.
    const frame = requestAnimationFrame(() =>
      setDraft(readReleasedDraft() ?? (id ? readDiscussionDraft(ownerId, id) : undefined))
    );
    return () => cancelAnimationFrame(frame);
  }, [ownerId, id, readReleasedDraft]);

  async function copy() {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
      toast.success(t('chat.discussions.draft_copied'));
    } catch {
      // Plain HTTP installations can still select and copy the field by hand.
      toast.error(t('chat.discussions.draft_copy_failed'));
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-lg gap-3 p-4">
      <p role="alert" className="text-sm text-destructive">
        {t(refused ? 'chat.discussions.unavailable' : 'chat.discussions.history_error')}
      </p>
      {draft && (
        <>
          <Textarea label={t('chat.discussions.draft_recovery')} value={draft} readOnly />
          <Button type="button" variant="outline" onClick={() => void copy()}>
            {t('chat.discussions.draft_copy')}
          </Button>
        </>
      )}
      <div className="flex flex-wrap gap-2">
        {id !== null && (
          <Button type="button" onClick={onMain}>
            {t('chat.discussions.back_main')}
          </Button>
        )}
        {!refused && (
          <Button type="button" variant="outline" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        )}
      </div>
    </div>
  );
}
