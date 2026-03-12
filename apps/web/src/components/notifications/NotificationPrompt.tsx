/**
 * Notification permission prompt component.
 *
 * Shows a dialog to request push notification permission.
 * Handles iOS PWA specific requirements.
 */

'use client';

import { Bell, Smartphone, Info } from 'lucide-react';
import { InfoBox } from '@/components/ui/info-box';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Alert, AlertContent, AlertIcon, AlertDescription } from '@/components/ui/alert';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { toast } from 'sonner';
import { logger } from '@/lib/logger';
import { useFCMToken } from '@/hooks/useFCMToken';
import { getDeviceType } from '@/lib/firebase';

interface NotificationPromptProps {
  lng: Language;
  /** Whether the dialog is open */
  open: boolean;
  /** Callback when dialog state changes */
  onOpenChange: (open: boolean) => void;
  /** Optional callback on successful permission grant */
  onSuccess?: (token: string) => void;
}

/**
 * Dialog component for requesting notification permissions.
 *
 * Important notes:
 * - On iOS, the app must be "Add to Home Screen" (PWA) to receive notifications
 * - Permission request MUST be triggered by user interaction (click)
 * - Only available on Safari 16.4+ for iOS
 *
 * @example
 * ```tsx
 * const [showPrompt, setShowPrompt] = useState(false);
 *
 * return (
 *   <>
 *     <Button onClick={() => setShowPrompt(true)}>
 *       Enable Notifications
 *     </Button>
 *     <NotificationPrompt
 *       lng={lng}
 *       open={showPrompt}
 *       onOpenChange={setShowPrompt}
 *       onSuccess={(token) => console.log('Token:', token)}
 *     />
 *   </>
 * );
 * ```
 */
export function NotificationPrompt({
  lng,
  open,
  onOpenChange,
  onSuccess,
}: NotificationPromptProps) {
  const { t } = useTranslation(lng);
  const {
    permissionStatus,
    isSupported,
    isConfigured,
    isIOSPWA,
    isLoading,
    error: fcmError,
    requestPermission,
    registeredTokens,
  } = useFCMToken();

  // Check if current device has a registered token
  const currentDeviceType = typeof window !== 'undefined' ? getDeviceType() : 'web';
  const hasCurrentDeviceToken = registeredTokens.some(
    t => t.device_type === currentDeviceType && t.is_active
  );

  const isIOS = typeof window !== 'undefined' && /iPhone|iPad|iPod/.test(navigator.userAgent);
  const needsIOSInstall = isIOS && !isIOSPWA;

  /**
   * Handle enable notifications button click.
   * This MUST be a direct user interaction for permission to work.
   */
  const handleEnableNotifications = async () => {
    logger.info('NotificationPrompt: User clicked enable', {
      component: 'NotificationPrompt',
      permissionStatus,
      isIOS,
      isIOSPWA,
    });

    const token = await requestPermission();

    if (token) {
      toast.success(t('notifications.enabled_success'));
      onSuccess?.(token);
      onOpenChange(false);
    } else {
      // Check if permission was denied
      if (permissionStatus === 'denied') {
        toast.error(t('notifications.permission_denied'));
      } else {
        // Show detailed error message in development for debugging
        const errorMsg = fcmError || t('notifications.enable_failed');
        console.error('[NotificationPrompt] Enable failed:', fcmError);
        toast.error(errorMsg);
      }
    }
  };

  // Don't render if not supported or not configured
  if (!isSupported) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              {t('notifications.title')}
            </DialogTitle>
          </DialogHeader>
          <Alert variant="warning">
            <AlertIcon variant="warning" />
            <AlertContent>
              <AlertDescription>{t('notifications.unsupported')}</AlertDescription>
            </AlertContent>
          </Alert>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  if (!isConfigured) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              {t('notifications.title')}
            </DialogTitle>
          </DialogHeader>
          <Alert variant="info">
            <AlertIcon variant="info" />
            <AlertContent>
              <AlertDescription>{t('notifications.not_configured')}</AlertDescription>
            </AlertContent>
          </Alert>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  // Already granted AND token registered for this device
  // FIX 2025-01-31: Only show "already enabled" if token exists for current device
  // When user disables notifications, permission stays 'granted' but token is deleted
  if (permissionStatus === 'granted' && hasCurrentDeviceToken) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bell className="h-5 w-5" />
              {t('notifications.title')}
            </DialogTitle>
          </DialogHeader>
          <Alert variant="success">
            <AlertIcon variant="success" />
            <AlertContent>
              <AlertDescription>{t('notifications.already_enabled')}</AlertDescription>
            </AlertContent>
          </Alert>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              {t('common.close')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Bell className="h-5 w-5" />
            {t('notifications.title')}
          </DialogTitle>
          <DialogDescription>{t('notifications.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* iOS specific warning: Need to install PWA */}
          {needsIOSInstall && (
            <Alert variant="warning">
              <AlertIcon variant="warning" />
              <AlertContent>
                <div className="space-y-2">
                  <p className="text-sm font-medium">{t('notifications.ios_pwa_required')}</p>
                  <div className="flex items-start gap-2 text-sm">
                    <Smartphone className="h-4 w-4 mt-0.5 shrink-0" />
                    <p>{t('notifications.ios_install_instructions')}</p>
                  </div>
                </div>
              </AlertContent>
            </Alert>
          )}

          {/* Permission denied warning */}
          {permissionStatus === 'denied' && (
            <Alert variant="error">
              <AlertIcon variant="error" />
              <AlertContent>
                <div className="space-y-2">
                  <p className="text-sm font-medium">{t('notifications.permission_blocked')}</p>
                  <p className="text-sm">{t('notifications.permission_blocked_help')}</p>
                </div>
              </AlertContent>
            </Alert>
          )}

          {/* Info about notifications */}
          <InfoBox>
            <div className="flex items-start gap-2">
              <Info className="h-4 w-4 text-muted-foreground mt-0.5 shrink-0" />
              <div className="flex-1 text-sm text-muted-foreground">
                <p>{t('notifications.info_text')}</p>
              </div>
            </div>
          </InfoBox>
        </div>

        <DialogFooter className="flex-col gap-2 sm:flex-row">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
            {t('common.later')}
          </Button>
          <Button
            onClick={handleEnableNotifications}
            disabled={isLoading || permissionStatus === 'denied' || needsIOSInstall}
          >
            {isLoading ? t('common.loading') : t('notifications.enable_button')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Small inline prompt for notification settings.
 * Can be used in settings page or as a banner.
 */
interface NotificationBannerProps {
  lng: Language;
  onEnableClick: () => void;
}

export function NotificationBanner({ lng, onEnableClick }: NotificationBannerProps) {
  const { t } = useTranslation(lng);
  const { permissionStatus, isSupported, isConfigured } = useFCMToken();

  // Don't show if not supported, not configured, or already granted
  if (!isSupported || !isConfigured || permissionStatus === 'granted') {
    return null;
  }

  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <Bell className="h-5 w-5 text-primary" />
        <div>
          <p className="text-sm font-medium">{t('notifications.banner_title')}</p>
          <p className="text-xs text-muted-foreground">{t('notifications.banner_description')}</p>
        </div>
      </div>
      <Button size="sm" onClick={onEnableClick}>
        {t('notifications.enable_button')}
      </Button>
    </div>
  );
}
