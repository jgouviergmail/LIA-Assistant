'use client';
import { useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { useLocalizedRouter } from '@/hooks/useLocalizedRouter';
import type { SmsReceivedSignal } from '@/lib/sms/notification';
/** The notice contains no sender or body, and stale account callbacks cannot navigate. */
export function useSmsReceivedToast(ownerId: string | undefined) {
  const { t } = useTranslation();
  const router = useLocalizedRouter();
  const { isCurrent, lifetime } = useApplicationAccountLifetime(ownerId);
  const notices = useRef(new Set<string>());
  useEffect(() => {
    const ids = new Set<string>();
    notices.current = ids;
    return () => {
      for (const id of ids) toast.dismiss(id);
    };
  }, [lifetime]);
  return useCallback(
    (signal: SmsReceivedSignal) => {
      if (!isCurrent() || signal.user_id !== ownerId) return;
      const id = `sms:${signal.occurrence_id}`;
      notices.current.add(id);
      toast.info(t('sms.new_received'), {
        id,
        duration: 5000,
        onAutoClose: () => {
          notices.current.delete(id);
        },
        onDismiss: () => {
          notices.current.delete(id);
        },
        action: {
          label: t('sms.archive'),
          onClick: () => {
            if (isCurrent())
              router.push(`/dashboard/sms?message=${encodeURIComponent(signal.message_id)}`);
          },
        },
      });
    },
    [isCurrent, ownerId, notices, t, router]
  );
}
