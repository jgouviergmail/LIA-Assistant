'use client';

import { useState } from 'react';
import { LockKeyhole } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import apiClient, { ApiStepUpError } from '@/lib/api-client';
import { Button } from '@/components/ui/button';
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
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import { useApiQuery } from '@/hooks/useApiQuery';
import { usePasskeys } from '@/hooks/useWebAuthn';
import { logger } from '@/lib/logger';

interface StepUpStatus {
  methods: string[];
  password_set: boolean;
  step_up_valid_until: string | null;
}

/**
 * Password sign-in block (arbitration A8): explicit disabling, allowed only
 * with ≥ 2 active passkeys, behind a fresh step-up. Email reset remains the
 * documented recovery path — stated in the UI copy, never silent.
 */
export function PasswordSettings() {
  const { t } = useTranslation();
  const { data: status, refetch } = useApiQuery<StepUpStatus>('/auth/step-up/status', {
    componentName: 'PasswordSettings',
  });
  const { passkeys } = usePasskeys();
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const passwordSet = Boolean(status?.password_set);
  const eligible = passwordSet && passkeys.length >= 2;

  const handleDisable = async () => {
    setBusy(true);
    try {
      await guard(() => apiClient.post('/auth/password/disable'));
      setConfirmOpen(false);
      toast.success(t('settings.security.password.disabled_toast'));
      await refetch();
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Password disable failed', err as Error, {
          component: 'PasswordSettings',
        });
        toast.error(t('settings.security.password.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <section aria-labelledby="security-password-title" className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3
            id="security-password-title"
            className="text-sm font-semibold flex items-center gap-2"
          >
            <LockKeyhole className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.security.password.title')}
          </h3>
          <p className="text-sm text-muted-foreground">
            {passwordSet
              ? t('settings.security.password.description_enabled')
              : t('settings.security.password.description_disabled')}
          </p>
          {passwordSet && !eligible && (
            <p className="text-xs text-muted-foreground">
              {t('settings.security.password.requirement_hint')}
            </p>
          )}
        </div>
        {passwordSet && (
          <Button
            size="sm"
            variant="outline"
            className="text-destructive shrink-0"
            onClick={() => setConfirmOpen(true)}
            disabled={!eligible}
          >
            {t('settings.security.password.disable')}
          </Button>
        )}
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={open => !busy && setConfirmOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('settings.security.password.disable_title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.password.disable_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDisable}
              disabled={busy}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {t('settings.security.password.disable_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />
    </section>
  );
}
