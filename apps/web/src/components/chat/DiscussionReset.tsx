'use client';

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { RotateCcw } from '@/lib/icons';
import type { ConversationSummary } from '@/types/conversation';
import { ConversationRetirementConfirm } from './ConversationRetirementConfirm';
import { ResetConversationConfirm } from './ResetConversationConfirm';

interface DiscussionResetProps {
  target: ConversationSummary | null;
  catalogueAvailable: boolean;
  available: boolean;
  reset: (target: ConversationSummary, operationId: string) => Promise<void>;
  legacyReset: () => Promise<void>;
}

export function DiscussionReset({
  target,
  catalogueAvailable,
  available,
  reset,
  legacyReset,
}: DiscussionResetProps) {
  const { t } = useTranslation();
  const [reviewed, setReviewed] = useState<ConversationSummary | null>(null);
  const [legacyOpen, setLegacyOpen] = useState(false);
  const [legacyPending, setLegacyPending] = useState(false);

  function open() {
    if (target) setReviewed({ ...target });
    else setLegacyOpen(true);
  }

  async function confirmLegacy() {
    setLegacyOpen(false);
    setLegacyPending(true);
    try {
      await legacyReset();
      toast.success(t('chat.conversation_reset_success'));
    } catch {
      toast.error(t('chat.conversation_reset_error'));
    } finally {
      setLegacyPending(false);
    }
  }

  return (
    <>
      <Button
        type="button"
        variant="destructive"
        size="sm"
        onClick={open}
        disabled={!available || (catalogueAvailable && target === null)}
        isLoading={legacyPending}
        aria-label={t('chat.new_chat')}
        className="min-h-10 min-w-10 shrink-0 rounded-full px-2.5"
      >
        <RotateCcw aria-hidden="true" />
        <span className="hidden @min-[640px]:inline">{t('chat.new_chat')}</span>
      </Button>
      <ResetConversationConfirm
        open={legacyOpen}
        onOpenChange={setLegacyOpen}
        onConfirm={() => void confirmLegacy()}
      />
      {reviewed && (
        <ConversationRetirementConfirm
          action="reset"
          target={reviewed}
          onConfirm={reset}
          onClose={() => setReviewed(null)}
        />
      )}
    </>
  );
}
