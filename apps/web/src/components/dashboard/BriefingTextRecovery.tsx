'use client';
import { useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';

/** An explicit retry survives its loading transition and owns focus only when it still has it. */
export function BriefingTextRecovery({
  unavailable,
  loading,
  onRetry,
  onRecovered,
}: {
  unavailable: boolean;
  loading: boolean;
  onRetry(): Promise<void>;
  onRecovered(): void;
}) {
  const { t } = useTranslation();
  const [requested, setRequested] = useState(false);
  const source = useRef<HTMLButtonElement | null>(null);
  if (requested && !loading && !unavailable) setRequested(false);
  const show = unavailable || requested;
  // Restore before the modal's MutationObserver repairs the removed button's
  // focus by moving it to the dialog itself.
  useLayoutEffect(() => {
    if (show || !source.current) return;
    if (!source.current.isConnected && document.activeElement === document.body) onRecovered();
    source.current = null;
  }, [show, onRecovered]);
  if (!show) return null;
  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-xl border bg-card p-3 text-sm"
      role="status"
    >
      <p className="min-w-0 flex-1">{t('dashboard.briefing.text_unavailable')}</p>
      <Button
        size="sm"
        variant="outline"
        isLoading={loading}
        onClick={event => {
          source.current = event.currentTarget;
          // Safari mouse activation need not focus a button. This explicit retry
          // owns attention until the person chooses another destination.
          event.currentTarget.focus();
          setRequested(true);
          // The briefing query owns and exposes transport failures.
          void onRetry().catch(() => {});
        }}
      >
        {t('common.retry')}
      </Button>
    </div>
  );
}
