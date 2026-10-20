'use client';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources } from '@/lib/application-resources';
import { SmsSignalInbox, type SmsReceivedSignal } from '@/lib/sms/notification';

/** Phone events invalidate source reads; they never enter the chat notification archive. */
export function useSmsNotificationSignals(
  ownerId: string | undefined,
  onReceived?: (signal: SmsReceivedSignal) => void
) {
  const { isCurrent } = useApplicationAccountLifetime(ownerId);
  const callback = useRef(onReceived);
  useEffect(() => {
    callback.current = onReceived;
  }, [onReceived]);
  const inbox = useMemo(() => new SmsSignalInbox(ownerId), [ownerId]);
  const refreshSms = useCallback(() => {
    if (ownerId && isCurrent()) publishApplicationResources(ownerId, new Set(['sms']));
  }, [ownerId, isCurrent]);
  const receiveSms = useCallback(
    (payload: unknown) => {
      if (!isCurrent()) return;
      const received = inbox.accept(payload);
      if (!received) return;
      refreshSms();
      callback.current?.(received);
    },
    [isCurrent, inbox, refreshSms]
  );
  return { receiveSms, refreshSms };
}
