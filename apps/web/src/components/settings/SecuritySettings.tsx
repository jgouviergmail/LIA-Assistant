'use client';

import { useState } from 'react';
import { Fingerprint, KeyRound, Pencil, Plus, Trash2 } from 'lucide-react';
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
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  useAuthFeatures,
  usePasskeys,
  useWebAuthn,
  type PasskeyCredential,
} from '@/hooks/useWebAuthn';
import { isWebAuthnSupported } from '@/lib/webauthn';
import { TotpSettings } from '@/components/settings/TotpSettings';
import { PasswordSettings } from '@/components/settings/PasswordSettings';
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import { ApiStepUpError } from '@/lib/api-client';
import { logger } from '@/lib/logger';

/**
 * Security settings — passkey management (security program D1, Lot 1).
 *
 * Lists registered passkeys with label/last-use, supports enrollment
 * (browser ceremony), rename, and revocation. Renders nothing when the
 * instance has MFA disabled (flag read from /auth/features). Renders as a
 * collapsible SettingsSection card like every other settings section.
 */
export function SecuritySettings({ collapsible = true }: { collapsible?: boolean } = {}) {
  const { t, i18n } = useTranslation();
  const { features } = useAuthFeatures();
  const mfaEnabled = Boolean(features?.mfa_enabled);
  const { passkeys, loading, refetch, renamePasskey, deletePasskey } = usePasskeys(mfaEnabled);
  const { registerPasskey } = useWebAuthn();
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();

  const formatDateTime = (iso: string): string =>
    new Date(iso).toLocaleString(i18n.language, {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

  const [addOpen, setAddOpen] = useState(false);
  const [addLabel, setAddLabel] = useState('');
  const [addBusy, setAddBusy] = useState(false);
  const [renameTarget, setRenameTarget] = useState<PasskeyCredential | null>(null);
  const [renameLabel, setRenameLabel] = useState('');
  const [renameBusy, setRenameBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PasskeyCredential | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  if (!mfaEnabled) return null;

  const browserSupported = isWebAuthnSupported();

  const handleAdd = async () => {
    setAddBusy(true);
    try {
      await guard(() => registerPasskey(addLabel.trim() || undefined));
      toast.success(t('settings.security.passkeys.added'));
      setAddOpen(false);
      setAddLabel('');
      await refetch();
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Passkey enrollment failed', err as Error, {
          component: 'SecuritySettings',
        });
        toast.error(t('settings.security.passkeys.add_error'));
      }
    } finally {
      setAddBusy(false);
    }
  };

  const handleRename = async () => {
    if (!renameTarget) return;
    setRenameBusy(true);
    try {
      await guard(() => renamePasskey(renameTarget.id, renameLabel.trim() || null));
      toast.success(t('settings.security.passkeys.renamed'));
      setRenameTarget(null);
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Passkey rename failed', err as Error, {
          component: 'SecuritySettings',
        });
        toast.error(t('settings.security.passkeys.rename_error'));
      }
    } finally {
      setRenameBusy(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleteBusy(true);
    try {
      await guard(() => deletePasskey(deleteTarget.id));
      toast.success(t('settings.security.passkeys.revoked'));
      setDeleteTarget(null);
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Passkey revocation failed', err as Error, {
          component: 'SecuritySettings',
        });
        toast.error(t('settings.security.passkeys.revoke_error'));
      }
    } finally {
      setDeleteBusy(false);
    }
  };

  const passkeyName = (passkey: PasskeyCredential): string =>
    passkey.label || t('settings.security.passkeys.unnamed');

  const content = (
    <div className="space-y-4">
      {/* Stacked on phones (the button drops UNDER the text), side by side
          from sm up — the row layout squeezed the description on 390px. */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1">
          <h4 className="text-sm font-semibold flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.security.passkeys.title')}
          </h4>
          <p className="text-sm text-muted-foreground">
            {t('settings.security.passkeys.description')}
          </p>
        </div>
        <Button
          size="sm"
          className="gap-1.5 self-start sm:shrink-0"
          onClick={() => setAddOpen(true)}
          disabled={!browserSupported}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('settings.security.passkeys.add')}
        </Button>
      </div>

      {!browserSupported && (
        <p className="text-sm text-muted-foreground">
          {t('settings.security.passkeys.unsupported_browser')}
        </p>
      )}

      {loading ? (
        <div className="flex justify-center py-6">
          <LoadingSpinner />
        </div>
      ) : passkeys.length === 0 ? (
        <p className="text-sm text-muted-foreground rounded-lg border border-dashed border-border px-4 py-6 text-center">
          {t('settings.security.passkeys.empty')}
        </p>
      ) : (
        <ul className="space-y-2">
          {passkeys.map(passkey => (
            <li
              key={passkey.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <div className="min-w-0 space-y-0.5">
                <div className="flex items-center gap-2">
                  <KeyRound className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />
                  <span className="text-sm font-medium truncate">{passkeyName(passkey)}</span>
                  {passkey.backed_up && (
                    // `success`, not grey: a synced passkey is a positive
                    // state, and grey is reserved for inactive ones.
                    <Badge variant="success" className="text-[10px]">
                      {t('settings.security.passkeys.synced')}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('settings.security.passkeys.created_at', {
                    date: formatDateTime(passkey.created_at),
                  })}
                  {passkey.last_used_at &&
                    ` · ${t('settings.security.passkeys.last_used', {
                      date: formatDateTime(passkey.last_used_at),
                    })}`}
                </p>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={t('settings.security.passkeys.rename_aria', {
                    name: passkeyName(passkey),
                  })}
                  onClick={() => {
                    setRenameTarget(passkey);
                    setRenameLabel(passkey.label ?? '');
                  }}
                >
                  <Pencil className="h-4 w-4" aria-hidden="true" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive"
                  aria-label={t('settings.security.passkeys.revoke_aria', {
                    name: passkeyName(passkey),
                  })}
                  onClick={() => setDeleteTarget(passkey)}
                >
                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Enrollment dialog */}
      <Dialog open={addOpen} onOpenChange={open => !addBusy && setAddOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.security.passkeys.add_title')}</DialogTitle>
            <DialogDescription>{t('settings.security.passkeys.add_description')}</DialogDescription>
          </DialogHeader>
          <Input
            label={t('settings.security.passkeys.label_input')}
            value={addLabel}
            onChange={e => setAddLabel(e.target.value)}
            placeholder={t('settings.security.passkeys.label_placeholder')}
            maxLength={64}
            disabled={addBusy}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)} disabled={addBusy}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleAdd} disabled={addBusy}>
              {addBusy
                ? t('settings.security.passkeys.add_pending')
                : t('settings.security.passkeys.add_confirm')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Rename dialog */}
      <Dialog
        open={renameTarget !== null}
        onOpenChange={open => !renameBusy && !open && setRenameTarget(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.security.passkeys.rename_title')}</DialogTitle>
          </DialogHeader>
          <Input
            label={t('settings.security.passkeys.label_input')}
            value={renameLabel}
            onChange={e => setRenameLabel(e.target.value)}
            placeholder={t('settings.security.passkeys.label_placeholder')}
            maxLength={64}
            disabled={renameBusy}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setRenameTarget(null)} disabled={renameBusy}>
              {t('common.cancel')}
            </Button>
            <Button onClick={handleRename} disabled={renameBusy}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="border-t border-border pt-4">
        <TotpSettings />
      </div>

      <div className="border-t border-border pt-4">
        <PasswordSettings />
      </div>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />

      {/* Revocation confirm */}
      <AlertDialog
        open={deleteTarget !== null}
        onOpenChange={open => !deleteBusy && !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.security.passkeys.revoke_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.passkeys.revoke_description', {
                name: deleteTarget ? passkeyName(deleteTarget) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleteBusy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} disabled={deleteBusy} variant="destructive">
              {t('settings.security.passkeys.revoke_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="security-auth"
      title={t('settings.security.auth.title')}
      description={t('settings.security.auth.description')}
      icon={Fingerprint}
    >
      {content}
    </SettingsSection>
  );
}
