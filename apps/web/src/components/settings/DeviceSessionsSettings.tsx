'use client';

import { useState } from 'react';
import { Laptop, LogOut, MonitorSmartphone, Smartphone } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { Badge } from '@/components/ui/badge';
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
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { StepUpDialog } from '@/components/auth/StepUpDialog';
import { useStepUpGuard } from '@/hooks/useStepUpGuard';
import { ApiStepUpError } from '@/lib/api-client';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useAuth } from '@/hooks/useAuth';
import {
  useLoginNotificationsPreference,
  useSessions,
  type DeviceSession,
} from '@/hooks/useSessions';
import { logger } from '@/lib/logger';

/**
 * "My devices" — live sessions of the account (security program D2).
 *
 * Bounded metadata only (coarse families, truncated IP); attested sessions
 * show their real device name (A4). Revoking one device is plain auth;
 * signing out every other device requires a fresh step-up. Detached
 * background runs (ADR-117) continue server-side — stated in the copy.
 * Renders as a collapsible SettingsSection card like every other section.
 */
export function DeviceSessionsSettings({ collapsible = true }: { collapsible?: boolean } = {}) {
  const { t, i18n } = useTranslation();
  const { sessions, loading, revokeSession, revokeOthers } = useSessions();
  const { guard, stepUpOpen, onVerified, onCancel } = useStepUpGuard();
  const { user, refreshUser } = useAuth();
  const { setEnabled: setLoginNotifications } = useLoginNotificationsPreference();
  const [notifBusy, setNotifBusy] = useState(false);

  const handleNotifToggle = async (enabled: boolean) => {
    setNotifBusy(true);
    try {
      await setLoginNotifications(enabled);
      await refreshUser();
    } catch (err) {
      logger.error('Login-notification preference failed', err as Error, {
        component: 'DeviceSessionsSettings',
      });
      toast.error(t('settings.security.devices.error_generic'));
    } finally {
      setNotifBusy(false);
    }
  };
  const [revokeTarget, setRevokeTarget] = useState<DeviceSession | null>(null);
  const [revokeAllOpen, setRevokeAllOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const formatDateTime = (iso: string): string =>
    new Date(iso).toLocaleString(i18n.language, {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    });

  const sessionName = (session: DeviceSession): string => {
    if (session.device_name) return session.device_name;
    if (session.ua_family || session.os_family) {
      const browser = session.ua_family ?? '';
      const os = session.os_family ?? '';
      return [browser, os].filter(Boolean).join(' · ');
    }
    return t('settings.security.devices.unknown_device');
  };

  const deviceIcon = (session: DeviceSession) => {
    if (session.os_family === 'ios' || session.os_family === 'android') {
      return <Smartphone className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />;
    }
    return <Laptop className="h-4 w-4 text-muted-foreground shrink-0" aria-hidden="true" />;
  };

  const handleRevoke = async () => {
    if (!revokeTarget) return;
    setBusy(true);
    try {
      await revokeSession(revokeTarget.id);
      toast.success(t('settings.security.devices.revoked'));
      setRevokeTarget(null);
    } catch (err) {
      logger.error('Session revocation failed', err as Error, {
        component: 'DeviceSessionsSettings',
      });
      toast.error(t('settings.security.devices.error_generic'));
    } finally {
      setBusy(false);
    }
  };

  const handleRevokeOthers = async () => {
    setBusy(true);
    try {
      const revoked = await guard(() => revokeOthers());
      setRevokeAllOpen(false);
      toast.success(t('settings.security.devices.others_revoked', { count: revoked }));
    } catch (err) {
      if (!(err instanceof ApiStepUpError)) {
        logger.error('Revoke-others failed', err as Error, {
          component: 'DeviceSessionsSettings',
        });
        toast.error(t('settings.security.devices.error_generic'));
      }
    } finally {
      setBusy(false);
    }
  };

  const content = (
    <div className="space-y-4">
      <div className="flex justify-end">
        {/* Mass destruction wears the same solid red as every "Delete all"
            (ADR-207 — owner arbitration 2026-08-05): it signs out every other
            device at once. */}
        <Button
          size="sm"
          variant="destructive"
          className="shrink-0 gap-1.5"
          onClick={() => setRevokeAllOpen(true)}
          disabled={sessions.length <= 1}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          {t('settings.security.devices.revoke_others')}
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-6">
          <LoadingSpinner />
        </div>
      ) : (
        <ul className="space-y-2">
          {sessions.map(session => (
            <li
              key={session.id}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3"
            >
              <div className="min-w-0 space-y-0.5">
                <div className="flex items-center gap-2">
                  {deviceIcon(session)}
                  <span className="text-sm font-medium truncate">{sessionName(session)}</span>
                  {session.current && (
                    <Badge variant="secondary" className="text-[10px]">
                      {t('settings.security.devices.current')}
                    </Badge>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  {session.ip_trunc &&
                    `${t('settings.security.devices.ip', { ip: session.ip_trunc })} · `}
                  {t('settings.security.devices.signed_in', {
                    date: formatDateTime(session.created_at),
                  })}
                  {session.last_seen_at &&
                    ` · ${t('settings.security.devices.last_seen', {
                      date: formatDateTime(session.last_seen_at),
                    })}`}
                </p>
              </div>
              {!session.current && (
                <Button
                  variant="ghost"
                  size="icon"
                  className="text-destructive hover:text-destructive shrink-0"
                  aria-label={t('settings.security.devices.revoke_aria', {
                    name: sessionName(session),
                  })}
                  onClick={() => setRevokeTarget(session)}
                >
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-3">
        <div className="space-y-0.5">
          <Label htmlFor="login-notifications-toggle" className="text-sm font-medium">
            {t('settings.security.devices.notify_title')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.security.devices.notify_description')}
          </p>
        </div>
        <Switch
          id="login-notifications-toggle"
          checked={user?.login_notifications_enabled ?? true}
          onCheckedChange={handleNotifToggle}
          disabled={notifBusy}
        />
      </div>

      <p className="text-xs text-muted-foreground">
        {t('settings.security.devices.background_runs_note')}
      </p>

      {/* Single revocation confirm */}
      <AlertDialog
        open={revokeTarget !== null}
        onOpenChange={open => !busy && !open && setRevokeTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t('settings.security.devices.revoke_title')}</AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.devices.revoke_description', {
                name: revokeTarget ? sessionName(revokeTarget) : '',
              })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevoke} disabled={busy} variant="destructive">
              {t('settings.security.devices.revoke_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Revoke-others confirm (step-up guarded) */}
      <AlertDialog open={revokeAllOpen} onOpenChange={open => !busy && setRevokeAllOpen(open)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('settings.security.devices.revoke_others_title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.security.devices.revoke_others_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={busy}>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleRevokeOthers} disabled={busy} variant="destructive">
              {t('settings.security.devices.revoke_others_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <StepUpDialog open={stepUpOpen} onVerified={onVerified} onCancel={onCancel} />
    </div>
  );

  if (!collapsible) {
    return content;
  }

  return (
    <SettingsSection
      value="security-devices"
      title={t('settings.security.devices.title')}
      description={t('settings.security.devices.description')}
      icon={MonitorSmartphone}
    >
      {content}
    </SettingsSection>
  );
}
