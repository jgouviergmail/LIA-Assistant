'use client';

import { useState } from 'react';
import { Copy, ShieldCheck, Smartphone } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { useTotp, type TotpEnrollment } from '@/hooks/useTotp';
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import { ApiStepUpError } from '@/lib/api-client';
import { logger } from '@/lib/logger';

/**
 * TOTP (authenticator app) block of the Security settings — enrollment via
 * QR + manual secret (revealed once), confirmation code, backup codes
 * (revealed once, copyable), disable, and regeneration.
 */
export function TotpSettings() {
  const { t } = useTranslation();
  const { status, enroll, confirm, disable, regenerateBackupCodes } = useTotp();
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();

  const [enrollment, setEnrollment] = useState<TotpEnrollment | null>(null);
  const [confirmCode, setConfirmCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [disableOpen, setDisableOpen] = useState(false);
  const [regenerateOpen, setRegenerateOpen] = useState(false);

  const active = Boolean(status?.active);

  const handleEnroll = async () => {
    setBusy(true);
    try {
      setEnrollment(await guard(() => enroll()));
      setConfirmCode('');
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('TOTP enrollment failed', err as Error, { component: 'TotpSettings' });
        toast.error(t('settings.security.totp.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async () => {
    setBusy(true);
    try {
      const codes = await guard(() => confirm(confirmCode.trim()));
      setEnrollment(null);
      setBackupCodes(codes);
      toast.success(t('settings.security.totp.activated'));
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('TOTP confirmation failed', err as Error, { component: 'TotpSettings' });
        toast.error(t('settings.security.totp.enroll_error'));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDisable = async () => {
    setBusy(true);
    try {
      await guard(() => disable());
      setDisableOpen(false);
      toast.success(t('settings.security.totp.disabled_toast'));
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('TOTP disable failed', err as Error, { component: 'TotpSettings' });
        toast.error(t('settings.security.totp.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async () => {
    setBusy(true);
    try {
      const codes = await guard(() => regenerateBackupCodes());
      setRegenerateOpen(false);
      setBackupCodes(codes);
      toast.success(t('settings.security.totp.regenerated'));
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Backup code regeneration failed', err as Error, {
          component: 'TotpSettings',
        });
        toast.error(t('settings.security.totp.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  const copyBackupCodes = async () => {
    if (!backupCodes) return;
    await navigator.clipboard.writeText(backupCodes.join('\n'));
    toast.success(t('settings.security.totp.backup_copied'));
  };

  return (
    <section aria-labelledby="security-totp-title" className="space-y-4">
      {/* Stacked on phones, side by side from `sm` up — the same header
          contract as the passkeys block above it: the fixed row squeezed the
          description against a column of two buttons on 390px. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h4 id="security-totp-title" className="text-sm font-semibold flex items-center gap-2">
            <Smartphone className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.security.totp.title')}
            {active && (
              // `success`, not grey: grey badges are reserved for INACTIVE
              // states (owner rule 2026-08-05), and this one says "enabled".
              <Badge variant="success" className="gap-1 text-[10px]">
                <ShieldCheck className="h-3 w-3" aria-hidden="true" />
                {t('settings.security.totp.status_active')}
              </Badge>
            )}
          </h4>
          <p className="text-sm text-muted-foreground">{t('settings.security.totp.description')}</p>
          {active && (
            <p className="text-xs text-muted-foreground">
              {t('settings.security.totp.codes_remaining', {
                count: status?.backup_codes_remaining ?? 0,
              })}
            </p>
          )}
        </div>
        {/* A switch, like every other feature toggle (owner arbitration
            2026-08-05). CONTROLLED by the server state on purpose: turning it
            on starts the enrollment ceremony (QR + code) and the thumb only
            moves once the server confirms; turning it off asks the house
            confirm first. */}
        <div className="flex flex-wrap items-center gap-2 self-start sm:shrink-0 sm:flex-col sm:items-end">
          <Switch
            checked={active}
            disabled={busy}
            aria-label={t('settings.security.totp.title')}
            onCheckedChange={value => {
              if (value) void handleEnroll();
              else setDisableOpen(true);
            }}
          />
          {active && (
            <Button size="sm" variant="outline" onClick={() => setRegenerateOpen(true)}>
              {t('settings.security.totp.regenerate')}
            </Button>
          )}
        </div>
      </div>

      {/* Enrollment dialog: QR + manual secret + confirmation code */}
      <Dialog
        open={enrollment !== null}
        onOpenChange={open => !busy && !open && setEnrollment(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.security.totp.enroll_title')}</DialogTitle>
            <DialogDescription>{t('settings.security.totp.enroll_description')}</DialogDescription>
          </DialogHeader>
          {enrollment && (
            <div className="space-y-4">
              <div className="flex justify-center">
                {/* eslint-disable-next-line @next/next/no-img-element -- data-URI QR, next/image adds nothing */}
                <img
                  src={enrollment.qr_data_uri}
                  alt={t('settings.security.totp.qr_alt')}
                  className="h-44 w-44 rounded-md border border-border bg-white p-2"
                />
              </div>
              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">
                  {t('settings.security.totp.enroll_secret_label')}
                </p>
                <code className="block select-all break-all rounded bg-muted px-2 py-1 text-xs">
                  {enrollment.secret}
                </code>
              </div>
              <Input
                label={t('settings.security.totp.enroll_code_label')}
                type="text"
                inputMode="numeric"
                value={confirmCode}
                onChange={e => setConfirmCode(e.target.value)}
                placeholder={t('settings.security.totp.enroll_code_placeholder')}
                maxLength={8}
                autoComplete="one-time-code"
                disabled={busy}
              />
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEnrollment(null)} disabled={busy}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleConfirm} disabled={busy || confirmCode.trim().length < 6}>
              {t('settings.security.totp.enroll_confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Backup codes dialog — revealed once */}
      <Dialog open={backupCodes !== null} onOpenChange={open => !open && setBackupCodes(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.security.totp.backup_title')}</DialogTitle>
            <DialogDescription>{t('settings.security.totp.backup_description')}</DialogDescription>
          </DialogHeader>
          <ul className="grid grid-cols-2 gap-2 font-mono text-sm">
            {(backupCodes ?? []).map(code => (
              <li key={code} className="select-all rounded bg-muted px-2 py-1 text-center">
                {code}
              </li>
            ))}
          </ul>
          <DialogFooter>
            <Button variant="outline" className="gap-1.5" onClick={copyBackupCodes}>
              <Copy className="h-4 w-4" aria-hidden="true" />
              {t('settings.security.totp.backup_copy')}
            </Button>
            <Button onClick={() => setBackupCodes(null)}>
              {t('settings.security.totp.backup_done')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Disable confirm */}
      <AlertDialog open={disableOpen} onOpenChange={open => !busy && setDisableOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.security.totp.disable_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.totp.disable_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDisable} disabled={busy} variant="destructive">
              {t('settings.security.totp.disable_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />

      {/* Regenerate confirm */}
      <AlertDialog open={regenerateOpen} onOpenChange={open => !busy && setRegenerateOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.security.totp.regenerate_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.totp.regenerate_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRegenerate} disabled={busy}>
              {t('settings.security.totp.regenerate')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
