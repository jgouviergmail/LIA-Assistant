'use client';

import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { BookUser } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApplicationAccountLifetime } from '@/hooks/useApplicationAccountLifetime';
import { publishApplicationResources } from '@/lib/application-resources';
import { cn } from '@/lib/utils';

/** Refresh data and refresh names are separate, explicit operations. */
export function SmsIdentityRefresh() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { isCurrent } = useApplicationAccountLifetime(user?.id);
  const inFlight = useRef(false);
  const [busy, setBusy] = useState(false);
  const { mutate } = useApiMutation<void, void>({
    method: 'POST',
    componentName: 'SmsIdentityRefresh',
    retainResponse: false,
  });
  const refresh = async () => {
    if (inFlight.current || !isCurrent() || !user) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await mutate('/sms/identities/refresh');
      if (isCurrent()) publishApplicationResources(user.id, new Set(['sms']));
    } catch {
      if (isCurrent()) toast.error(t('sms.unavailable'));
    } finally {
      inFlight.current = false;
      if (isCurrent()) setBusy(false);
    }
  };
  return (
    <Button variant="outline" aria-disabled={busy} aria-busy={busy} onClick={() => void refresh()}>
      <BookUser className={cn('h-4 w-4', busy && 'motion-safe:animate-pulse')} aria-hidden="true" />
      {t('sms.refresh_names')}
    </Button>
  );
}
