'use client';

/**
 * « Keep talking? » — the explicit extension of a live session (wave 2 spec
 * A8). Shown by the controller `extension_prompt_seconds` before the cap;
 * counts the seconds left; Extend asks the API for the published minutes,
 * Let it end closes the dialog and the session ends at its cap. Unlimited
 * extensions, each explicit — a provider that bills the duration tolls
 * through a silence, so nobody extends by default.
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import type { UseLiveSessionReturn } from '@/hooks/useLiveSession';
import { useLiveStore } from '@/stores/liveStore';

export interface LiveExtendDialogProps {
  session: Pick<UseLiveSessionReturn, 'extend' | 'declineExtension'>;
}

/**
 * The seconds until the cap, refreshed every second. Mounted with the dialog's
 * content (Radix unmounts it when closed), so the first value is fresh and no
 * effect sets state directly.
 */
function SecondsLeft({ expiresAt, minutes }: { expiresAt: number | null; minutes: number }) {
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  const seconds = expiresAt === null ? 0 : Math.max(0, Math.ceil((expiresAt - now) / 1000));
  return <>{t('live.extend.body', { count: seconds, minutes })}</>;
}

export function LiveExtendDialog({ session }: LiveExtendDialogProps) {
  const { t } = useTranslation();
  const offered = useLiveStore(state => state.extensionOffered);
  const expiresAt = useLiveStore(state => state.expiresAt);
  const minutes = useLiveStore(state => state.extensionMinutes);
  const [busy, setBusy] = useState(false);

  const extend = async () => {
    if (busy) return;
    setBusy(true);
    const ok = await session.extend();
    setBusy(false);
    if (!ok) toast.error(t('live.extend.failed'));
  };

  return (
    <AlertDialog open={offered} onOpenChange={open => !open && session.declineExtension()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t('live.extend.title')}</AlertDialogTitle>
          <AlertDialogDescription>
            <SecondsLeft expiresAt={expiresAt} minutes={minutes} />
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={session.declineExtension} className="min-h-11">
            {t('live.extend.decline')}
          </AlertDialogCancel>
          <AlertDialogAction onClick={() => void extend()} disabled={busy} className="min-h-11">
            {t('live.extend.confirm', { minutes })}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
