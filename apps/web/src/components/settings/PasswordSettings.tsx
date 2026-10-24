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

/** What a reset request leaves the account once it holds no password (ADR-363). */
type PasswordRecovery = 'email_link' | 'provider' | 'none';

interface StepUpStatus {
  methods: string[];
  password_set: boolean;
  step_up_valid_until: string | null;
  password_recovery: PasswordRecovery;
  sign_in_provider: string | null;
}

/**
 * The way back the copy states, beside a password already off and in the
 * dialog that turns one off: the provider the account signs in with (an
 * administrator's included), nothing for an administrator without one,
 * otherwise the email reset link.
 */
function wayBack(status: StepUpStatus | undefined): PasswordRecovery {
  if (status?.sign_in_provider) return 'provider';
  return status?.password_recovery === 'none' ? 'none' : 'email_link';
}

const OFF_DESCRIPTION: Record<PasswordRecovery, string> = {
  email_link: 'settings.security.password.description_disabled',
  provider: 'settings.security.password.description_provider',
  none: 'settings.security.password.description_no_recovery',
};

const DISABLE_DESCRIPTION: Record<PasswordRecovery, string> = {
  email_link: 'settings.security.password.disable_description',
  provider: 'settings.security.password.disable_description_provider',
  none: 'settings.security.password.disable_description_no_recovery',
};

/**
 * Password sign-in block (arbitration A8): explicit disabling, allowed only
 * with ≥ 2 active passkeys, behind a fresh step-up. What remains to recover
 * the account is the reset decision's own answer (ADR-363), read from the
 * step-up status and stated in the UI copy, never silent.
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
  const recovery = wayBack(status);
  const withProvider = { provider: status?.sign_in_provider ?? '' };

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
      {/* Stacked on phones, side by side from `sm` up — the passkeys header
          contract, applied to all three security sub-blocks alike. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h4
            id="security-password-title"
            className="text-sm font-semibold flex items-center gap-2"
          >
            <LockKeyhole className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.security.password.title')}
          </h4>
          <p className="text-sm text-muted-foreground">
            {passwordSet
              ? t('settings.security.password.description_enabled')
              : t(OFF_DESCRIPTION[recovery], withProvider)}
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
            className="text-destructive self-start sm:shrink-0"
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
            <AlertDialogTitle>{t('settings.security.password.disable_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t(DISABLE_DESCRIPTION[recovery], withProvider)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDisable} disabled={busy} variant="destructive">
              {t('settings.security.password.disable_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />
    </section>
  );
}
