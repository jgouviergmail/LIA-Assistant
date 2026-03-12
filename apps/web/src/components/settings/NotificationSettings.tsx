'use client';

import * as React from 'react';
import { Bell, Smartphone, Monitor, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useFCMToken } from '@/hooks/useFCMToken';
import { NotificationPrompt } from '@/components/notifications/NotificationPrompt';
import { toast } from 'sonner';
import { getDeviceType } from '@/lib/firebase';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';

interface NotificationSettingsProps {
  lng: Language;
}

/**
 * Icon for device type
 */
function DeviceIcon({ type }: { type: string }) {
  switch (type) {
    case 'ios':
    case 'android':
      return <Smartphone className="h-4 w-4" />;
    default:
      return <Monitor className="h-4 w-4" />;
  }
}

export function NotificationSettings({ lng }: NotificationSettingsProps) {
  const { t } = useTranslation(lng);
  const {
    permissionStatus,
    isSupported,
    isConfigured,
    isLoading,
    registeredTokens,
    unregisterToken,
    refreshTokens,
  } = useFCMToken();

  const [showPrompt, setShowPrompt] = React.useState(false);
  const [deletingTokenId, setDeletingTokenId] = React.useState<string | null>(null);
  const [showDisableConfirm, setShowDisableConfirm] = React.useState(false);

  // Find current device token
  const currentDeviceType = typeof window !== 'undefined' ? getDeviceType() : 'web';
  const currentDeviceToken = registeredTokens.find(t => t.device_type === currentDeviceType && t.is_active);

  // Handle token deletion
  const handleDeleteToken = async (tokenId: string) => {
    setDeletingTokenId(tokenId);
    try {
      await unregisterToken(tokenId);
      toast.success(t('settings.notifications.device_removed'));
    } catch {
      toast.error(t('settings.notifications.device_remove_error'));
    } finally {
      setDeletingTokenId(null);
    }
  };

  // Handle disabling notifications for current device
  const handleDisableCurrentDevice = async () => {
    if (!currentDeviceToken) return;

    setDeletingTokenId(currentDeviceToken.id);
    try {
      await unregisterToken(currentDeviceToken.id);
      toast.success(t('settings.notifications.disabled_success'));
    } catch {
      toast.error(t('settings.notifications.device_remove_error'));
    } finally {
      setDeletingTokenId(null);
      setShowDisableConfirm(false);
    }
  };

  // Handle successful permission grant
  const handlePermissionSuccess = () => {
    refreshTokens();
  };

  return (
    <>
      <SettingsSection
        value="notifications"
        title={t('settings.notifications.title')}
        description={t('settings.notifications.description')}
        icon={Bell}
      >
        <div className="space-y-6">
          {/* Status Section - Switch toggle */}
          <div className="flex items-center justify-between p-3 rounded-lg border bg-card">
            <div className="flex-1">
              <Label htmlFor="notifications-switch" className="text-sm font-medium cursor-pointer">
                {t('settings.notifications.enable_notifications')}
              </Label>
              <p className="text-xs text-muted-foreground">
                {t('settings.notifications.enable_description')}
              </p>
            </div>
            <Switch
              id="notifications-switch"
              checked={isSupported && isConfigured && permissionStatus === 'granted' && !!currentDeviceToken}
              onCheckedChange={(checked) => {
                if (checked) {
                  // Enable: show permission prompt
                  setShowPrompt(true);
                } else if (currentDeviceToken) {
                  // Disable: show confirmation
                  setShowDisableConfirm(true);
                }
              }}
              disabled={
                !isSupported ||
                !isConfigured ||
                permissionStatus === 'denied' ||
                isLoading ||
                (currentDeviceToken && deletingTokenId === currentDeviceToken.id)
              }
            />
          </div>

          {/* Not configured warning */}
          {isSupported && !isConfigured && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4">
              <p className="text-sm text-amber-600">
                {t('settings.notifications.not_configured_admin')}
              </p>
            </div>
          )}

          {/* Permission denied help */}
          {permissionStatus === 'denied' && (
            <InfoBox variant="error" className="p-4">
              <p className="text-sm text-red-600">{t('settings.notifications.permission_denied_help')}</p>
            </InfoBox>
          )}

          {/* Registered Devices */}
          {permissionStatus === 'granted' && registeredTokens.length > 0 && (
            <div className="space-y-3">
              <h4 className="text-sm font-medium">{t('settings.notifications.registered_devices')}</h4>
              <div className="space-y-2">
                {registeredTokens.map((token) => (
                  <div
                    key={token.id}
                    className="flex items-center justify-between rounded-lg border p-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="rounded-lg bg-muted p-2">
                        <DeviceIcon type={token.device_type} />
                      </div>
                      <div>
                        <p className="text-sm font-medium">
                          {token.device_name || t(`settings.notifications.device_${token.device_type}`)}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {token.is_active
                            ? t('settings.notifications.device_active')
                            : t('settings.notifications.device_inactive')}
                        </p>
                      </div>
                    </div>

                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          disabled={deletingTokenId === token.id}
                        >
                          {deletingTokenId === token.id ? (
                            <LoadingSpinner size="default" />
                          ) : (
                            <Trash2 className="h-4 w-4 text-destructive" />
                          )}
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>
                            {t('settings.notifications.remove_device_title')}
                          </AlertDialogTitle>
                          <AlertDialogDescription>
                            {t('settings.notifications.remove_device_description')}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleDeleteToken(token.id)}>
                            {t('common.delete')}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* No devices registered */}
          {permissionStatus === 'granted' && registeredTokens.length === 0 && !isLoading && (
            <div className="rounded-lg border border-dashed p-4 text-center">
              <p className="text-sm text-muted-foreground">
                {t('settings.notifications.no_devices')}
              </p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center p-4">
              <LoadingSpinner size="lg" spinnerColor="muted" />
            </div>
          )}

          {/* Info text */}
          <InfoBox className="p-4">
            <p className="text-sm text-muted-foreground">{t('settings.notifications.info_text')}</p>
          </InfoBox>
        </div>
      </SettingsSection>

      {/* Notification Permission Dialog */}
      <NotificationPrompt
        lng={lng}
        open={showPrompt}
        onOpenChange={setShowPrompt}
        onSuccess={handlePermissionSuccess}
      />

      {/* Disable Notifications Confirmation Dialog */}
      <AlertDialog open={showDisableConfirm} onOpenChange={setShowDisableConfirm}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {t('settings.notifications.disable_title')}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {t('settings.notifications.disable_description')}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t('common.cancel')}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDisableCurrentDevice}>
              {t('settings.notifications.disable_confirm')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
